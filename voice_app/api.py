import json
import frappe
import os
import re
import time
import traceback
import pandas as pd
import requests
import urllib.parse
from contextlib import suppress
from voice_app.utils.activity_logger import ActivityLogger
from frappe.utils.file_manager import save_file
from voice_app.gemini_stt_client import call_gemini_stt
from voice_app.task_extractor import extract_tasks_only, create_tasks_to_erp
from voice_app.docx_utils import save_to_docx
from voice_app.audio_utils import convert_to_wav
from voice_app.speaker_manager import get_segment_embedding, SpeakerDB
from voice_app.constants import SIMILARITY_THRESHOLD

_logger = ActivityLogger("VOICE", "voice_app")

def _build_speaker_alias_map(speakers):
    """Map UI display labels back to the canonical Voice Speaker name."""
    aliases = {}
    rows = list(speakers or [])
    for speaker in rows:
        name = str(speaker.get("speaker_name") or "").strip()
        if name:
            aliases[name] = name

    # Canonical rows overwrite accidental labels such as
    # "Name - email - Voice Speaker" created by the old dropdown value.
    for speaker in rows:
        name = str(speaker.get("speaker_name") or "").strip()
        email = str(speaker.get("email") or "").strip()
        if not name:
            continue
        aliases[f"{name} - Voice Speaker"] = name
        if email and email != "Chưa cập nhật":
            aliases[f"{name} - {email} - Voice Speaker"] = name
            aliases[f"{name} - {email}"] = name
    return aliases


def _get_speaker_alias_map():
    with suppress(Exception):
        speakers = frappe.get_all("Voice Speaker", fields=["speaker_name", "email"])
        return _build_speaker_alias_map(speakers)
    return {}


def _normalize_requested_speaker_name(value, aliases=None):
    text = str(value or "").strip()
    if not text:
        return ""
    # Bóc icon người ở đầu nhãn. Giao diện luôn hiển thị "👤 Tên", nên nếu giữ
    # nguyên icon thì "👤 chị Thuỷ" bị coi là người khác với "chị Thuỷ" — đã
    # tái hiện: một lần quét lại tạo thêm bản ghi "👤 chị Thuỷ" nằm song song
    # với bản ghi thật trong Voice Speaker.
    text = re.sub(r"^[\U0001F464\U0001F465\U0001F466-\U0001F469‍️\s]+", "", text).strip()
    if not text:
        return ""
    aliases = aliases or _get_speaker_alias_map()
    direct = aliases.get(text)
    if direct:
        return direct

    legacy = text
    suffix = " - Voice Speaker"
    while legacy.endswith(suffix):
        legacy = legacy[: -len(suffix)].strip()
        if not legacy:
            break
        mapped = aliases.get(legacy)
        if mapped:
            return mapped

    return legacy or text


def _pick_top_ranked_match(ranked):
    """Return the highest-scoring DB match when it passes the base threshold."""
    ranked = list(ranked or [])
    if not ranked:
        return None
    top = ranked[0]
    return top if float(top[1]) >= SIMILARITY_THRESHOLD else None


def _top_db_match(db, embedding, allowed_names=None, aliases=None):
    aliases = aliases or _get_speaker_alias_map()
    allowed = None
    if allowed_names:
        allowed = {_normalize_requested_speaker_name(name, aliases) for name in allowed_names}

    ranked = []
    for row in db.rank_all(embedding, allowed_names=allowed):
        name = row[0]
        canonical = aliases.get(name, name)
        # Ignore an accidental composite duplicate when its canonical record is
        # already present; its sample must not compete with the real DB row.
        if canonical != name and canonical in db.speakers:
            continue
        ranked.append(row)
    return _pick_top_ranked_match(ranked), ranked

def _can_access_meeting(meeting_owner, user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True
    if meeting_owner == user:
        return True
    with suppress(Exception):
        return "System Manager" in frappe.get_roles(user)
    return False


def _seg_get(seg, key, idx=None, default=None):
    if isinstance(seg, dict):
        return seg.get(key, default)
    if idx is not None and len(seg) > idx:
        return seg[idx]
    return default


def _seg_set_speaker_value(seg, value):
    if isinstance(seg, dict):
        seg["speaker"] = value
    elif len(seg) > 2:
        seg[2] = value


def _has_segment_embedding(seg):
    emb = _seg_get(seg, "embedding", 4, None)
    if emb is None:
        return False
    if isinstance(emb, (list, tuple)) and not emb:
        return False
    return True


def _segment_duration(seg):
    try:
        start = float(_seg_get(seg, "start", 0, 0) or 0)
        end = float(_seg_get(seg, "end", 1, start) or start)
    except Exception:
        return 0.0
    return max(0.0, end - start)


def _segment_text(seg):
    return str(_seg_get(seg, "text", 3, "") or "").strip()


def _build_plain_transcript(results):
    return " ".join(_segment_text(seg) for seg in results if _segment_text(seg))


def _audio_file_url_to_path(file_url):
    clean_url = (file_url or "").strip()
    if not clean_url:
        return ""
    if clean_url.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        clean_url = urlparse(clean_url).path
    clean_url = clean_url.lstrip("/")
    if clean_url.startswith("files/"):
        return frappe.get_site_path("public", clean_url)
    return frappe.get_site_path(clean_url)


def _ensure_file_attachment(file_url, attached_to_doctype, attached_to_name, file_name=None, is_private=None):
    clean_url = str(file_url or "").strip()
    if not clean_url or not attached_to_doctype or not attached_to_name:
        return None

    existing_name = frappe.db.get_value(
        "File",
        {
            "file_url": clean_url,
            "attached_to_doctype": attached_to_doctype,
            "attached_to_name": attached_to_name,
        },
        "name",
    )
    if existing_name:
        return frappe.get_doc("File", existing_name)

    source_name = frappe.db.get_value("File", {"file_url": clean_url}, "name")
    if source_name:
        source = frappe.get_doc("File", source_name)
        if not source.attached_to_doctype and not source.attached_to_name:
            source.attached_to_doctype = attached_to_doctype
            source.attached_to_name = attached_to_name
            if is_private is not None:
                source.is_private = int(bool(is_private))
            source.save(ignore_permissions=True)
            return source

        clone = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name or source.file_name or os.path.basename(clean_url),
                "file_url": clean_url,
                "folder": source.folder,
                "file_size": source.file_size,
                "content_hash": source.content_hash,
                "is_private": int(bool(source.is_private if is_private is None else is_private)),
                "attached_to_doctype": attached_to_doctype,
                "attached_to_name": attached_to_name,
            }
        )
        clone.insert(ignore_permissions=True)
        return clone

    doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name or os.path.basename(clean_url),
            "file_url": clean_url,
            "is_private": int(bool(is_private if is_private is not None else clean_url.startswith("/private/"))),
            "attached_to_doctype": attached_to_doctype,
            "attached_to_name": attached_to_name,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _missing_audio_rescan_error(meeting):
    title = str(getattr(meeting, "title", "") or getattr(meeting, "name", "") or "").strip()
    suffix = f" ({title})" if title else ""
    return {
        "status": "error",
        "message": (
            f"Meeting này không có file âm thanh gốc{suffix}, nên không thể quét lại AI / trích giọng."
            " Hãy dùng meeting có audio gốc hoặc upload lại audio để chạy luồng này."
        ),
    }


def _seg_set_embedding_value(seg, value):
    emb_list = value.tolist() if hasattr(value, "tolist") else value
    if isinstance(seg, dict):
        seg["embedding"] = emb_list
        return
    if len(seg) > 4:
        seg[4] = emb_list
        return
    while len(seg) < 4:
        seg.append("")
    seg.append(emb_list)


def _rebuild_segment_embeddings_from_audio(meeting, original_results, force=False, min_duration=0.8, task="Rebuild segment embeddings"):
    """
    Re-extract per-segment embeddings from the original meeting audio.
    This intentionally overwrites old speaker-level representative embeddings
    when force=True, because those vectors can point to the wrong audio for a
    specific transcript segment.
    """
    from voice_app.speaker_manager import _extract_embeddings_from_files_remote

    audio_path = _audio_file_url_to_path(meeting.audio_file)
    if not audio_path or not os.path.exists(audio_path):
        return {
            "rebuilt_count": 0,
            "skipped_count": len(original_results or []),
            "failed_count": 0,
            "error": "Không tìm thấy file âm thanh gốc để trích xuất giọng nói.",
        }

    wav_path = ""
    try:
        wav_path, err = convert_to_wav(audio_path)
        if err:
            return {
                "rebuilt_count": 0,
                "skipped_count": len(original_results or []),
                "failed_count": 0,
                "error": f"Lỗi xử lý file âm thanh: {err}",
            }

        items = []
        indexes = []
        skipped_count = 0
        for idx, seg in enumerate(original_results or []):
            if not force and _has_segment_embedding(seg):
                skipped_count += 1
                continue
            start = float(_seg_get(seg, "start", 0, 0) or 0)
            end = float(_seg_get(seg, "end", 1, start) or start)
            if end - start < float(min_duration or 0):
                skipped_count += 1
                continue
            indexes.append(idx)
            items.append({"wav_path": wav_path, "start": start, "end": end})

        if not items:
            return {"rebuilt_count": 0, "skipped_count": skipped_count, "failed_count": 0, "error": ""}

        emb_results = _extract_embeddings_from_files_remote(items, task=task)
        rebuilt_count = 0
        failed_count = 0
        for idx, emb in zip(indexes, emb_results or []):
            if emb is None:
                failed_count += 1
                continue
            _seg_set_embedding_value(original_results[idx], emb)
            rebuilt_count += 1

        return {
            "rebuilt_count": rebuilt_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "error": "",
        }
    finally:
        if wav_path and os.path.exists(wav_path):
            with suppress(FileNotFoundError):
                os.remove(wav_path)


def _normalize_np_embedding(emb):
    import numpy as np

    if emb is None:
        return None
    emb_np = np.array(emb, dtype=np.float32)
    norm = np.linalg.norm(emb_np)
    if norm > 0:
        emb_np = emb_np / norm
    return emb_np


def _clean_speaker_sample_embedding(wav_path, start, end, fallback_embedding=None, task="Lọc sample giọng trước khi lưu DB"):
    """
    For long selected segments, split into short windows and keep the most
    self-consistent run. This avoids saving a Voice Speaker embedding polluted
    by another speaker at the head/tail of a diarized segment.
    """
    import numpy as np
    from scipy.spatial.distance import cosine
    from voice_app.speaker_manager import _extract_embeddings_from_files_remote

    duration = max(0.0, float(end or start) - float(start or 0))
    fallback = _normalize_np_embedding(fallback_embedding)

    if not wav_path or not os.path.exists(wav_path) or duration < 1.5:
        return {"embedding": fallback, "start": start, "end": end, "windows": 0, "kept_windows": 0}

    win = 2.0
    step = 1.0
    max_sample_duration = 12.0
    windows = []
    pos = float(start)
    while pos + 1.5 <= float(end):
        w_end = min(float(end), pos + win)
        if w_end - pos >= 1.5:
            windows.append({"wav_path": wav_path, "start": pos, "end": w_end})
        pos += step
    if not windows:
        return {"embedding": fallback, "start": start, "end": end, "windows": 0, "kept_windows": 0}

    emb_results = _extract_embeddings_from_files_remote(windows, task=task)
    valid = []
    for idx, emb in enumerate(emb_results or []):
        emb_np = _normalize_np_embedding(emb)
        if emb_np is not None:
            valid.append((idx, emb_np))
    if not valid:
        return {"embedding": fallback, "start": start, "end": end, "windows": len(windows), "kept_windows": 0}
    if len(valid) == 1:
        idx, emb_np = valid[0]
        return {"embedding": emb_np, "start": windows[idx]["start"], "end": windows[idx]["end"], "windows": len(windows), "kept_windows": 1}

    sims = []
    for idx, emb_np in valid:
        avg = sum(float(1 - cosine(emb_np, other)) for _, other in valid if other is not emb_np) / max(1, len(valid) - 1)
        sims.append((avg, idx, emb_np))
    sims.sort(reverse=True, key=lambda item: item[0])
    score_by_idx = {idx: avg for avg, idx, _ in sims}
    _, medoid_idx, medoid = sims[0]

    kept_indexes = sorted(
        idx for idx, emb_np in valid
        if float(1 - cosine(medoid, emb_np)) >= 0.50
    )
    if not kept_indexes:
        kept_indexes = [medoid_idx]

    runs = []
    current = [kept_indexes[0]]
    for idx in kept_indexes[1:]:
        if idx == current[-1] + 1:
            current.append(idx)
        else:
            runs.append(current)
            current = [idx]
    runs.append(current)
    best_run = max(runs, key=len)

    max_windows = max(1, int((max_sample_duration - win) / step) + 1)
    if len(best_run) > max_windows:
        candidates = []
        for offset in range(0, len(best_run) - max_windows + 1):
            subset = best_run[offset : offset + max_windows]
            score = sum(score_by_idx.get(idx, 0.0) for idx in subset)
            includes_medoid = medoid_idx in subset
            candidates.append((includes_medoid, score, subset))
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_run = candidates[0][2]

    run_embeddings = [emb_np for idx, emb_np in valid if idx in best_run]
    avg_emb = np.mean(np.stack(run_embeddings), axis=0)
    avg_emb = _normalize_np_embedding(avg_emb)

    return {
        "embedding": avg_emb,
        "start": windows[best_run[0]]["start"],
        "end": windows[best_run[-1]]["end"],
        "windows": len(windows),
        "kept_windows": len(best_run),
    }


def _raw_result_speaker_label(original_seg, idx=0, fallback_by_source=None):
    raw_label = str(
        _seg_get(original_seg, "raw_speaker", None, "")
        or _seg_get(original_seg, "speaker", 2, "")
        or ""
    ).strip()
    if raw_label:
        if raw_label.startswith("👤 ") and not any(
            marker in raw_label for marker in ("Speaker", "Người lạ", "Unknown", "Không tên")
        ):
            return raw_label[2:].strip()
        return raw_label

    source = str(
        _seg_get(original_seg, "source_speaker", None, "")
        or _seg_get(original_seg, "speaker_id", None, "")
        or _seg_get(original_seg, "source", None, "")
        or f"segment_{idx + 1}"
    ).strip()
    if fallback_by_source is None:
        return source or f"segment_{idx + 1}"
    if source not in fallback_by_source:
        fallback_by_source[source] = f"👤 Speaker {len(fallback_by_source) + 1} [{source}]"
    return fallback_by_source[source]


def _is_meaningful_transcript_text(text):
    import re
    t = str(text or "").strip()
    t_clean = re.sub(r'^(?:\.{2,}\s*)|(?:\s*\.{2,})$', '', t).strip()
    if not t_clean:
        return False
    if re.fullmatch(r'[\W\d]+', t_clean):
        return False
    t_lower = " ".join(t_clean.lower().split())
    hallucinations = {
        "xong rồi gì nữa",
        "em xích lên cho",
        "cảm ơn các bạn",
        "xin chào",
        "tạm biệt",
        "cảm ơn",
        "hết",
        "chào các bạn",
        "ừ",
        "ừm",
        "ờ",
        "ok",
        "dạ",
        "vâng",
        "dạ vâng",
        "à",
        "ờm",
    }
    if t_lower in hallucinations and len(t_clean.split()) <= 5:
        return False
    return True


def _merge_adjacent_same_speaker_segments(results, original_results):
    """
    Merge only transcript segments that are already adjacent and already share
    the same final speaker label. This is a final formatting pass for rescans,
    not a diarization heuristic.
    """
    results = list(results or [])
    original_results = list(original_results or [])
    if not results:
        return results, original_results, 0

    def _as_original_dict(seg):
        if isinstance(seg, dict):
            row = dict(seg)
        else:
            row = {
                "start": _seg_get(seg, "start", 0, 0),
                "end": _seg_get(seg, "end", 1, 0),
                "speaker": _seg_get(seg, "speaker", 2, ""),
                "text": _seg_get(seg, "text", 3, ""),
                "embedding": _seg_get(seg, "embedding", 4, None),
            }
        row["_embedding_duration"] = _segment_duration(seg) if _has_segment_embedding(seg) else 0.0
        if "raw_speaker" not in row:
            row["raw_speaker"] = str(row.get("speaker") or "").strip()
        return row

    def _result_clone(seg, speaker, text, end):
        if isinstance(seg, dict):
            row = dict(seg)
            row["speaker"] = speaker
            row["text"] = text
            row["end"] = end
            return row
        row = list(seg) if isinstance(seg, (list, tuple)) else [0, 0, "", ""]
        while len(row) < 4:
            row.append("")
        row[2] = speaker
        row[3] = text
        if len(row) > 1:
            row[1] = end
        return row

    def _join_text(left, right):
        left_text = str(left or "").strip()
        right_text = str(right or "").strip()
        if not left_text:
            return right_text
        if not right_text:
            return left_text
        if right_text[:1] in ",.;:!?)]}":
            return f"{left_text}{right_text}"
        return f"{left_text} {right_text}"

    if len(original_results) < len(results):
        original_results.extend(results[len(original_results):])

    merged_results = []
    merged_original_results = []
    merged_count = 0

    for idx, display_seg in enumerate(results):
        current_label = str(_seg_get(display_seg, "speaker", 2, "") or "").strip()
        original_seg = _as_original_dict(
            original_results[idx] if idx < len(original_results) else display_seg
        )
        original_seg["speaker"] = str(original_seg.get("speaker") or "").strip()
        original_seg["raw_speaker"] = str(
            original_seg.get("raw_speaker") or original_seg.get("speaker") or ""
        ).strip()

        if not merged_results:
            merged_results.append(_result_clone(display_seg, current_label, _segment_text(display_seg), float(_seg_get(display_seg, "end", 1, 0) or 0)))
            merged_original_results.append(original_seg)
            continue

        previous_label = str(_seg_get(merged_results[-1], "speaker", 2, "") or "").strip()
        if not current_label or current_label != previous_label:
            merged_results.append(_result_clone(display_seg, current_label, _segment_text(display_seg), float(_seg_get(display_seg, "end", 1, 0) or 0)))
            merged_original_results.append(original_seg)
            continue

        merged_count += 1
        previous_result = merged_results[-1]
        previous_original = merged_original_results[-1]

        new_end = float(_seg_get(display_seg, "end", 1, _seg_get(previous_result, "end", 1, 0)) or 0)
        new_text = _join_text(_segment_text(previous_result), _segment_text(display_seg))

        if isinstance(previous_result, dict):
            previous_result["end"] = new_end
            previous_result["text"] = new_text
        else:
            previous_result[1] = new_end
            previous_result[3] = new_text

        previous_original["end"] = float(original_seg.get("end") or previous_original.get("end") or 0)
        previous_original["text"] = _join_text(previous_original.get("text"), original_seg.get("text"))

        prev_raw = str(previous_original.get("raw_speaker") or previous_original.get("speaker") or "").strip()
        curr_raw = str(original_seg.get("raw_speaker") or original_seg.get("speaker") or "").strip()
        if prev_raw != curr_raw:
            previous_original["raw_speaker"] = current_label
            previous_original["speaker"] = current_label

        for key in ("source_speaker", "speaker_id", "source", "source_chunk", "chunk"):
            prev_val = str(previous_original.get(key) or "").strip()
            curr_val = str(original_seg.get(key) or "").strip()
            if prev_val != curr_val:
                previous_original[key] = ""

        prev_emb_dur = float(previous_original.get("_embedding_duration") or 0.0)
        curr_emb_dur = float(original_seg.get("_embedding_duration") or 0.0)
        if curr_emb_dur > prev_emb_dur and _has_segment_embedding(original_seg):
            previous_original["embedding"] = original_seg.get("embedding")
            previous_original["_embedding_duration"] = curr_emb_dur

    for row in merged_original_results:
        row.pop("_embedding_duration", None)

    return merged_results, merged_original_results, merged_count


def _restore_result_speakers_from_original(results, original_results):
    """Reset display labels to Gemini/chunk raw labels before applying DB matches."""
    restored = 0
    fallback_by_source = {}

    for idx, display_seg in enumerate(results or []):
        original_seg = original_results[idx] if idx < len(original_results or []) else display_seg
        raw_label = _raw_result_speaker_label(original_seg, idx, fallback_by_source)
        if isinstance(original_seg, dict) and not str(original_seg.get("speaker") or "").strip():
            original_seg["speaker"] = raw_label
        current = str(_seg_get(display_seg, "speaker", 2, "") or "").strip()
        if current == raw_label:
            continue
        _seg_set_speaker_value(display_seg, raw_label)
        restored += 1
    return restored


def _segment_source_key(seg, fallback_label=""):
    source = str(
        _seg_get(seg, "source_speaker", None, "")
        or _seg_get(seg, "speaker_id", None, "")
        or _seg_get(seg, "source", None, "")
        or ""
    ).strip()
    if source:
        return f"source:{source}"
    label = str(_seg_get(seg, "speaker", 2, fallback_label) or fallback_label or "").strip()
    return f"label:{label}" if label else ""


def _segment_chunk_key(seg):
    chunk = str(
        _seg_get(seg, "source_chunk", None, "")
        or _seg_get(seg, "chunk", None, "")
        or ""
    ).strip()
    return f"chunk:{chunk}" if chunk else ""


def _build_manual_speaker_assignments(results, original_results, mappings):
    """
    Convert UI mappings such as 'Speaker 1 [c5_speaker_3]' -> 'Nguyễn Văn A'
    into source-level rules. These rules are user-confirmed and should apply to
    every segment from the same Gemini/chunk speaker, even when embedding score
    is below the DB threshold.
    """
    assignments = {}
    mapped_labels = {str(old).strip(): str(new).strip() for old, new in (mappings or {}).items() if str(old).strip() and str(new).strip()}
    if not mapped_labels:
        return assignments

    for idx, display_seg in enumerate(results or []):
        current_label = str(_seg_get(display_seg, "speaker", 2, "") or "").strip()
        new_label = mapped_labels.get(current_label)
        if not new_label:
            continue
        original_seg = original_results[idx] if idx < len(original_results or []) else display_seg
        source_key = _segment_source_key(original_seg, current_label)
        if source_key:
            assignments[source_key] = new_label
        assignments[f"label:{current_label}"] = new_label
    return assignments


def _build_manual_assignment_from_segment(results, original_results, segment_index, speaker_name):
    if segment_index < 0 or segment_index >= len(results or []):
        return {}
    display_seg = results[segment_index]
    original_seg = original_results[segment_index] if segment_index < len(original_results or []) else display_seg
    current_label = str(_seg_get(display_seg, "speaker", 2, "") or "").strip()
    speaker_name = str(speaker_name or "").strip()
    if not speaker_name:
        return {}
    assignments = {}
    source_key = _segment_source_key(original_seg, current_label)
    if source_key:
        assignments[source_key] = speaker_name
    if current_label:
        assignments[f"label:{current_label}"] = speaker_name
    return assignments


def _is_unknown_label_text(label):
    text = str(label or "").strip()
    if not text:
        return True
    return any(marker in text for marker in ("Speaker", "Người lạ", "Unknown", "Không tên"))


def _build_manual_assignments_from_current_results(results, original_results, aliases=None):
    assignments = {}
    sample_indexes = {}
    sample_durations = {}
    fallback_by_source = {}
    aliases = aliases or _get_speaker_alias_map()

    for idx, display_seg in enumerate(results or []):
        current_label = _normalize_requested_speaker_name(
            _seg_get(display_seg, "speaker", 2, ""),
            aliases,
        )
        if _is_unknown_label_text(current_label):
            continue

        original_seg = original_results[idx] if idx < len(original_results or []) else display_seg
        original_label = _raw_result_speaker_label(original_seg, idx, fallback_by_source)
        if current_label == original_label:
            continue

        source_key = _segment_source_key(original_seg, current_label)
        if source_key:
            assignments[source_key] = current_label

        start = float(_seg_get(original_seg, "start", 0, 0) or 0)
        end = float(_seg_get(original_seg, "end", 1, start) or start)
        duration = max(0.0, end - start)
        if duration > sample_durations.get(current_label, 0.0):
            sample_durations[current_label] = duration
            sample_indexes[current_label] = idx

    return assignments, sample_indexes


def _apply_manual_speaker_assignments(results, original_results, assignments):
    if not assignments:
        return {"count": 0, "by_speaker": {}}
    count = 0
    by_speaker = {}
    for idx, display_seg in enumerate(results or []):
        original_seg = original_results[idx] if idx < len(original_results or []) else display_seg
        current_label = str(_seg_get(display_seg, "speaker", 2, "") or "").strip()
        source_key = _segment_source_key(original_seg, current_label)
        new_label = assignments.get(source_key) or assignments.get(f"label:{current_label}")
        if not new_label or current_label == new_label:
            continue
        _seg_set_speaker_value(display_seg, new_label)
        count += 1
        by_speaker[new_label] = by_speaker.get(new_label, 0) + 1
    return {"count": count, "by_speaker": dict(sorted(by_speaker.items(), key=lambda item: item[1], reverse=True))}


def _assign_by_source_winners(results, original_results, matched_indexes):
    """
    If Gemini/chunk diarization already groups several segments under the same
    source_speaker, use DB-matched segments in that source as votes and apply
    the top-voted real name to the rest of that same source. If a source has no
    votes, fall back to the top-voted real name in the whole chunk.
    """
    from collections import Counter, defaultdict

    matched_indexes = set(matched_indexes or [])
    source_votes = defaultdict(Counter)
    chunk_votes = defaultdict(Counter)
    unknown_markers = ("Speaker", "Người lạ", "Unknown", "Không tên")

    def _is_known_label(label):
        text = str(label or "").strip()
        return bool(text) and not any(marker in text for marker in unknown_markers)

    for idx in matched_indexes:
        if idx >= len(results or []) or idx >= len(original_results or []):
            continue
        original_seg = original_results[idx]
        source_key = _segment_source_key(original_seg, _seg_get(results[idx], "speaker", 2, ""))
        chunk_key = _segment_chunk_key(original_seg)
        label = str(_seg_get(results[idx], "speaker", 2, "") or "").strip()
        if source_key and _is_known_label(label):
            source_votes[source_key][label] += 1
        if chunk_key and _is_known_label(label):
            chunk_votes[chunk_key][label] += 1

    source_winners = {}
    for source_key, votes in source_votes.items():
        top = votes.most_common(1)
        if top:
            source_winners[source_key] = top[0][0]

    chunk_winners = {}
    for chunk_key, votes in chunk_votes.items():
        top = votes.most_common(1)
        if top:
            chunk_winners[chunk_key] = top[0][0]

    count = 0
    by_speaker = {}
    for idx, display_seg in enumerate(results or []):
        if idx in matched_indexes:
            continue
        original_seg = original_results[idx] if idx < len(original_results or []) else display_seg
        current = str(_seg_get(display_seg, "speaker", 2, "") or "").strip()
        # Inheritance is only a rescue path for unresolved/raw stranger labels.
        # A known label may still be overwritten by its own accepted embedding,
        # but never by another segment's source/chunk vote.
        if _is_known_label(current):
            continue
        source_key = _segment_source_key(original_seg, _seg_get(display_seg, "speaker", 2, ""))
        chunk_key = _segment_chunk_key(original_seg)
        winner = source_winners.get(source_key) or chunk_winners.get(chunk_key)
        if not winner:
            continue
        if current == winner:
            continue
        _seg_set_speaker_value(display_seg, winner)
        count += 1
        by_speaker[winner] = by_speaker.get(winner, 0) + 1

    return {
        "count": count,
        "by_speaker": dict(sorted(by_speaker.items(), key=lambda item: item[1], reverse=True)),
        "source_winners": source_winners,
        "chunk_winners": chunk_winners,
    }


@frappe.whitelist(allow_guest=False)
def transcribe_audio(language="vi", filter_speakers=None, stt_mode="google", num_speakers=None, custom_vocabulary=""):
    if 'file' not in frappe.request.files:
        frappe.throw("Thiếu file âm thanh")

    stt_mode = "google"
    audio_file = frappe.request.files['file']
    from datetime import datetime
    
    # Dùng cùng thuật toán hash với File.content_hash của Frappe.
    # Frappe hiện lưu MD5; tự tính SHA-256 sẽ không bao giờ match file cũ.
    from frappe.utils.file_manager import get_content_hash
    content = audio_file.read()
    content_hash = get_content_hash(content)
    audio_file.seek(0)
    
    # Tìm xem file này đã upload chưa (Deduplication)
    existing_file = frappe.db.get_value("File", {"content_hash": content_hash}, "file_url")
    if existing_file:
        file_url = existing_file
        file_path = frappe.get_site_path(file_url.strip('/'))

        # Ưu tiên kết quả đã hoàn tất của cùng file, kể cả khi một
        # lần upload trùng sau đó bị lỗi hoặc bị ngắt giữa chừng.
        existing_meetings = frappe.get_all(
            "Voice Meeting",
            filters={"audio_file": file_url},
            fields=["name", "status"],
            order_by="creation desc",
        )
        completed_meeting = next(
            (m for m in existing_meetings if m.status in ("Completed", "Analyzed", "Synced")),
            None,
        )
        if completed_meeting:
            _ensure_file_attachment(
                file_url,
                "Voice Meeting",
                completed_meeting.name,
                file_name=audio_file.filename,
                is_private=1,
            )
            return check_meeting_status(completed_meeting.name)

        active_meeting = next(
            (m for m in existing_meetings if m.status in ("Processing", "Pending")),
            None,
        )
        if active_meeting:
            _ensure_file_attachment(
                file_url,
                "Voice Meeting",
                active_meeting.name,
                file_name=audio_file.filename,
                is_private=1,
            )
            return check_meeting_status(active_meeting.name)

        retryable_meeting = next(
            (m for m in existing_meetings if m.status in ("Error", "Partial Error")),
            None,
        )
        if retryable_meeting:
            frappe.db.set_value("Voice Meeting", retryable_meeting.name, "status", "Processing")
            frappe.db.commit()
            meeting_doc = frappe.get_doc("Voice Meeting", retryable_meeting.name)
            _ensure_file_attachment(
                file_url,
                "Voice Meeting",
                meeting_doc.name,
                file_name=audio_file.filename,
                is_private=1,
            )
        else:
            meeting_title = f"Meeting - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            meeting_doc = frappe.get_doc({
                "doctype": "Voice Meeting",
                "title": meeting_title,
                "date": frappe.utils.now(),
                "status": "Processing",
                "audio_file": file_url,
                "language": language,
                "stt_mode": stt_mode,
                "num_speakers": num_speakers,
                "custom_vocabulary": custom_vocabulary,
                "filter_speakers": filter_speakers
            })
            meeting_doc.insert(ignore_permissions=True)
            _ensure_file_attachment(
                file_url,
                "Voice Meeting",
                meeting_doc.name,
                file_name=audio_file.filename,
                is_private=1,
            )
            frappe.db.commit()
    else:
        meeting_title = f"Meeting - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        meeting_doc = frappe.get_doc({
            "doctype": "Voice Meeting",
            "title": meeting_title,
            "date": frappe.utils.now(),
            "status": "Processing",
            "language": language,
            "stt_mode": stt_mode,
            "num_speakers": num_speakers,
            "custom_vocabulary": custom_vocabulary,
            "filter_speakers": filter_speakers
        })
        meeting_doc.insert(ignore_permissions=True)
        file_doc = save_file(audio_file.filename, content, "Voice Meeting", meeting_doc.name, is_private=1)
        file_path = frappe.get_site_path(file_doc.file_url.strip('/'))
        file_url = file_doc.file_url
        meeting_doc.db_set("audio_file", file_url, update_modified=False)
        frappe.db.commit()
    
    session_id_header = frappe.request.headers.get("X-App-Session-Id", "")

    frappe.enqueue(
        'voice_app.api._transcribe_audio_async',
        queue='long',
        timeout=3600,
        job_id=f"voice-transcribe-{meeting_doc.name}",
        deduplicate=False,
        file_path=file_path,
        file_url=file_url,
        filter_speakers=filter_speakers,
        stt_mode=stt_mode,
        meeting_name=meeting_doc.name,
        session_id_header=session_id_header,
        language=language,
        num_speakers=num_speakers,
        custom_vocabulary=custom_vocabulary
    )

    return {"status": "processing", "meeting_name": meeting_doc.name}

def get_cached_employees(ttl=300):
    cache_key = "cterp_employees_cache"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    from voice_app.constants import get_worksuite_url, get_worksuite_token
    import requests
    try:
        token = get_worksuite_token()
        session = requests.Session()
        base_url = get_worksuite_url()
        session.headers.update({"Authorization": f"token {token}", "Accept": "application/json"})
        emp_resp = session.get(
            f"{base_url}/api/resource/Employee",
            params={
                "fields": '["name","employee_name","user_id","designation","department"]',
                "filters": '[["status","=","Active"]]',
                "limit_page_length": 5000,
            },
            timeout=30,
        )
        if emp_resp.status_code == 200:
            employees = emp_resp.json().get("data", [])
            frappe.cache().set_value(cache_key, employees, expires_in_sec=ttl)
            return employees
    except Exception as exc:
        frappe.log_error(str(exc), "Get Cached Employees Error")
    return []

@frappe.whitelist(allow_guest=False)
def check_meeting_status(meeting_name):
    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    frappe.log_error(f"check_meeting_status called for {meeting_name}, status={meeting.status}", "Meeting Status Debug")
    if meeting.status in ("Completed", "Analyzed", "Synced"):
        raw_employees = get_cached_employees()
        employees = [e for e in raw_employees if e.get("user_id")]

        raw_results = []
        try:
            if meeting.raw_results:
                raw_results = json.loads(meeting.raw_results)
        except (TypeError, json.JSONDecodeError) as exc:
            frappe.log_error(str(exc), "Parse Meeting Raw Results Error")
            
        return {
            "status": "success",
            "results": raw_results,
            "final_text": meeting.transcript,
            "employees": employees,
            "meeting_name": meeting.name
        }
    elif meeting.status in ("Error", "Partial Error"):
        # Check custom field if exists
        error_msg = meeting.get("error_message") or "Có lỗi xảy ra khi xử lý âm thanh."
        return {"status": "error", "message": error_msg}
    else:
        progress_info = frappe.cache().get_value(f"transcribe_progress_{meeting.name}")
        return {"status": "processing", "meeting_name": meeting.name, "progress_info": progress_info}


def _append_stt_parse_log(doctype, docname, lines, max_chars=200000):
    """Append STT parse/runtime logs to a DocType field without failing the main pipeline."""
    if not docname or not lines:
        return
    if isinstance(lines, str):
        lines = [lines]
    lines = [str(line).strip() for line in lines if str(line).strip()]
    if not lines:
        return

    try:
        if not frappe.db.has_column(doctype, "stt_parse_log"):
            return
        old_log = frappe.db.get_value(doctype, docname, "stt_parse_log") or ""
        from frappe.utils import now_datetime
        stamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        new_block = "\n".join(f"[{stamp}] {line}" for line in lines)
        combined = f"{old_log.rstrip()}\n{new_block}".strip() if old_log else new_block
        if len(combined) > max_chars:
            combined = combined[-max_chars:]
        frappe.db.set_value(doctype, docname, "stt_parse_log", combined, update_modified=False)
    except Exception as exc:
        with suppress(Exception):
            frappe.log_error(str(exc), f"Append STT Parse Log Failed: {doctype}")


def _gemini_stt_cost(prompt_tokens=0, completion_tokens=0):
    price_in = 1.50 / 1_000_000
    price_out = 9.00 / 1_000_000
    return (int(prompt_tokens or 0) * price_in) + (int(completion_tokens or 0) * price_out)


def _sync_meeting_stt_usage(meeting_name, cost_user, model=None, fallback_prompt_tokens=0, fallback_completion_tokens=0):
    totals = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(stt_prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(stt_completion_tokens), 0) AS completion_tokens,
            COALESCE(SUM(stt_total_tokens), 0) AS total_tokens,
            COALESCE(SUM(stt_cost_usd), 0) AS cost_usd
        FROM `tabVoice Meeting Chunk`
        WHERE meeting = %s
        """,
        (meeting_name,),
        as_dict=True,
    )[0]
    prompt_tokens = int(totals.prompt_tokens or 0)
    completion_tokens = int(totals.completion_tokens or 0)
    total_tokens = int(totals.total_tokens or 0)
    cost_usd = float(totals.cost_usd or 0)

    if not total_tokens and (fallback_prompt_tokens or fallback_completion_tokens):
        prompt_tokens = int(fallback_prompt_tokens or 0)
        completion_tokens = int(fallback_completion_tokens or 0)
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = _gemini_stt_cost(prompt_tokens, completion_tokens)

    frappe.db.set_value("Voice Meeting", meeting_name, {
        "stt_prompt_tokens": prompt_tokens,
        "stt_completion_tokens": completion_tokens,
        "stt_total_tokens": total_tokens,
        "stt_cost_usd": cost_usd,
        "stt_cost_user": cost_user,
        "stt_model": model or f"google/{frappe.db.get_single_value('Voice App Settings', 'gemini_model') or 'gemini'}"
    })


def _transcribe_audio_async(file_path=None, file_url=None, filter_speakers=None, stt_mode="google", meeting_name=None, session_id_header=None, **kwargs):
    try:
        stt_mode = "google"
    
    
        pass
    
        try:
            def update_progress(stt_percent, stt_msg, spk_percent, spk_msg):
                progress_data = {
                    "stt": {"progress": stt_percent, "msg": stt_msg},
                    "speaker": {"progress": spk_percent, "msg": spk_msg}
                }
                frappe.cache().set_value(f"transcribe_progress_{meeting_name}", progress_data)
                
                # Publish event to all users connected to this site (or specific user if we pass user filter)
                frappe.publish_realtime(
                    "transcribe_progress",
                    {"meeting_name": meeting_name, "progress_info": progress_data},
                    after_commit=False
                )

            update_progress(5, "Đang chuẩn bị file âm thanh...", 0, "Chờ dịch văn bản...")

            # Convert to WAV
            wav, err = convert_to_wav(file_path)
            if err:
                if segments:
                    results_json = json.dumps(segments, ensure_ascii=False)
                    frappe.db.set_value("Voice Meeting", meeting_name, {
                        "status": "Partial Error",
                        "error_message": err,
                        "raw_results": results_json,
                        "original_raw_results": results_json
                    })
                else:
                    frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err})
                frappe.db.commit()
                return

                frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err}); frappe.db.commit(); return
    
            auto_num_speakers = kwargs.get("num_speakers")
                    
            global_vocabulary = kwargs.get("custom_vocabulary") or frappe.db.get_single_value("Voice App Settings", "global_vocabulary") or ""
            language = kwargs.get("language") or "vi"
    
            # Call STT theo mode
            def stt_cb(percent, msg):
                update_progress(percent, msg, 0, "Chờ dịch văn bản...")

            if stt_mode == "google":
                from voice_app.audio_utils import split_audio_by_silence
                import os
                import time
                
                chunk_dir = frappe.utils.get_site_path('private', 'files', 'voice_chunk', meeting_name)
                os.makedirs(chunk_dir, exist_ok=True)
                
                # Không còn chia nhỏ 5-10 phút/chunk — gửi nguyên audio cho Gemini
                # trong 1 lần gọi (giống AI Studio). Cap 4 tiếng chỉ để chặn file
                # cực lớn bất thường, meeting bình thường luôn ra đúng 1 chunk.
                raw_chunks = split_audio_by_silence(
                    wav, chunk_length_sec=14400.0, max_chunk_sec=14400.0, output_dir=chunk_dir
                )
                
                chunks_info = []
                for idx, c in enumerate(raw_chunks):
                    chunk_name = frappe.db.get_value("Voice Meeting Chunk", {"meeting": meeting_name, "chunk_index": idx}, "name")
                    if not chunk_name:
                        doc = frappe.get_doc({
                            "doctype": "Voice Meeting Chunk",
                            "meeting": meeting_name,
                            "chunk_index": idx,
                            "status": "Pending",
                            "audio_file_path": c[0],
                            "offset_sec": c[1]
                        })
                        doc.insert(ignore_permissions=True)
                        chunk_name = doc.name
                        status = "Pending"
                    else:
                        status = frappe.db.get_value("Voice Meeting Chunk", chunk_name, "status")
                    
                    chunks_info.append({
                        "name": chunk_name,
                        "idx": idx,
                        "wav": c[0],
                        "offset": c[1],
                        "mappings": c[2] if len(c) > 2 else [],
                        "status": status
                    })
                frappe.db.commit()
                
                chunks_to_process = [c for c in chunks_info if c["status"] in ("Pending", "Error", "Processing")]
                
                site_name = frappe.local.site
                meeting_cost_user = frappe.db.get_value("Voice Meeting", meeting_name, "owner") or frappe.session.user
                def chunk_update_cb(c_name, c_status, c_segs, c_words, c_err, c_toks, c_parse_logs=None, c_usage=None):
                    import frappe
                    try:
                        if c_parse_logs:
                            _append_stt_parse_log("Voice Meeting Chunk", c_name, c_parse_logs)
                            _append_stt_parse_log("Voice Meeting", meeting_name, c_parse_logs)
                        if c_status == "Processing":
                            frappe.db.set_value("Voice Meeting Chunk", c_name, "status", "Processing")
                        elif c_status == "Completed":
                            usage = c_usage or {}
                            prompt_tokens = int(usage.get("prompt_tokens") or 0)
                            completion_tokens = int(usage.get("completion_tokens") or 0)
                            total_tokens = int(usage.get("tokens_used") or c_toks or 0)
                            cost_usd = float(usage.get("cost_usd") or _gemini_stt_cost(prompt_tokens, completion_tokens))
                            frappe.db.set_value("Voice Meeting Chunk", c_name, {
                                "status": "Completed",
                                "raw_segments": json.dumps({"segments": c_segs, "raw_words": c_words}, ensure_ascii=False),
                                "tokens_used": c_toks,
                                "stt_prompt_tokens": prompt_tokens,
                                "stt_completion_tokens": completion_tokens,
                                "stt_total_tokens": total_tokens,
                                "stt_cost_usd": cost_usd,
                                "stt_cost_user": meeting_cost_user,
                                "stt_model": usage.get("model") or "google/gemini",
                                "error_message": ""
                            })
                        elif c_status == "Error":
                            frappe.db.set_value("Voice Meeting Chunk", c_name, {
                                "status": "Error",
                                "error_message": c_err
                            })
                        frappe.db.commit()
                    except Exception as e:
                        print(f"Error in chunk_update_cb: {e}")

                err, el_chars_used, el_chars_remaining = None, 0, 0
                if chunks_to_process:
                    frappe.log_error(
                        title="Transcribe Debug",
                        message=f"Bat dau chay {len(chunks_to_process)} chunks vao call_gemini_stt",
                    )
                    _segs, _raw, _txt, err, el_chars_used, el_chars_remaining = call_gemini_stt(
                        chunks_info=chunks_to_process, chunk_update_cb=chunk_update_cb,
                        language=language, num_speakers=auto_num_speakers, 
                        custom_vocabulary=global_vocabulary, progress_callback=stt_cb,
                        parse_log_cb=lambda c_name, lines: _append_stt_parse_log("Voice Meeting", meeting_name, lines)
                    )
                    frappe.log_error(
                        title="Transcribe Debug",
                        message=f"Goi call_gemini_stt hoan tat. Err={err}",
                    )
                    total_prompt_tokens = int(el_chars_used or 0)
                    total_completion_tokens = int(el_chars_remaining or 0)
                    _sync_meeting_stt_usage(
                        meeting_name,
                        meeting_cost_user,
                        fallback_prompt_tokens=total_prompt_tokens,
                        fallback_completion_tokens=total_completion_tokens,
                    )
                    frappe.db.commit()
                
                segments = []
                raw_words = []
                full_text = ""
                chunk_docs = frappe.get_all("Voice Meeting Chunk", filters={"meeting": meeting_name}, fields=["status", "raw_segments", "error_message"], order_by="chunk_index asc")
                
                has_error = False
                for c in chunk_docs:
                    if c.status != "Completed":
                        has_error = True
                        err = f"Lỗi ở chunk: {c.error_message}" if not err else err
                        frappe.log_error(
                            title="Transcribe Debug",
                            message=(
                                f"Phat hien chunk {c.name} (index {c.get('chunk_index', 'N/A')}) "
                                f"chua completed. Status={c.status}, Error={c.error_message}"
                            ),
                        )
                        break
                    if c.raw_segments:
                        try:
                            data = json.loads(c.raw_segments)
                            if data.get("segments"): segments.extend(data["segments"])
                            if data.get("raw_words"): raw_words.extend(data["raw_words"])
                        except Exception as e:
                            frappe.log_error(f"Loi json.loads raw_segments chunk {c.name}: {e}", "Transcribe Debug")
                            pass
                
                if has_error:
                    # Update status to Partial Error so it can be resumed
                    if segments:
                        frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Partial Error", "error_message": err, "raw_results": json.dumps(segments, ensure_ascii=False)})
                    else:
                        frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err})
                    frappe.db.commit()
                    return
                
                segments.sort(key=lambda x: x.get('start', 0))
                full_text = " ".join(s.get("text", "") for s in segments)
                
                # STT Hoàn tất thành công, dọn dẹp file chunk
                import shutil
                with suppress(FileNotFoundError):
                    shutil.rmtree(frappe.utils.get_site_path('private', 'files', 'voice_chunk', meeting_name))
            else:
                err = "STT mode không hỗ trợ. Hệ thống chỉ dùng Google Gemini."
                frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": err})
                frappe.db.commit()
                return
    
            stt_label = "Google Gemini" if stt_mode == "google" else "ElevenLabs"
            el_speakers = set(s["speaker_id"] for s in segments)
            print(f"[{stt_label}] {len(segments)} segments, {len(el_speakers)} speakers: {sorted(el_speakers)}")
            _append_stt_parse_log(
                "Voice Meeting",
                meeting_name,
                f"[{stt_label}] {len(segments)} segments, {len(el_speakers)} speakers: {sorted(el_speakers)}",
            )
    
            # ── SPEAKER IDENTIFICATION ─────────────────────────────────────────────
            from voice_app.speaker_manager import SpeakerDB
            import numpy as np

            update_progress(100, "Đã dịch xong văn bản!", 20, "Bắt đầu nhận diện người nói...")
            spk_db = SpeakerDB()
            unique_speakers = {}
            for seg in segments:
                spk = seg["speaker_id"]
                if spk not in unique_speakers:
                    unique_speakers[spk] = []
                unique_speakers[spk].append(seg)
    
            # Trích xuất embedding cho mỗi speaker_id từ ElevenLabs
            # Dùng concat nhiều đoạn → embedding đại diện hơn 1 đoạn ngắn
            from scipy.spatial.distance import cosine as cos_dist
            from voice_app.audio_utils import concat_speaker_segments
            spk_embeddings = {}  # speaker_id -> embedding
            spk_identified = {}  # speaker_id -> (name, score, email, user_info)
    
            total_spk = len(unique_speakers)
            completed_spk = 0

            
            files_list = []
            spk_list = []

            # Lọc tinh: Gemini đôi khi gán nhầm 1 phần nhỏ lời của người khác
            # vào cùng speaker_id (đo thực tế: có group lẫn ~23% đoạn của
            # người khác, làm centroid gộp bị lai, giảm độ chính xác nhận
            # diện). Probe từng đoạn so với DB, loại đoạn lệch hẳn khỏi đa số
            # trước khi build centroid cuối.
            from voice_app.speaker_manager import purify_speaker_group
            for spk in list(unique_speakers.keys()):
                kept, dropped = purify_speaker_group(
                    unique_speakers[spk], wav, spk_db, task="Lọc tinh trước khi gộp centroid"
                )
                if dropped:
                    _append_stt_parse_log(
                        "Voice Meeting",
                        meeting_name,
                        f"[Speaker] Lọc {len(dropped)} đoạn lệch khỏi {spk} (nghi gán nhầm người khác).",
                    )
                    unique_speakers[spk] = kept

            for spk, segs in unique_speakers.items():
                concat_wav = concat_speaker_segments(wav, segs, max_total_sec=25.0, min_seg_sec=1.5)
                if concat_wav is None:
                    # Fallback: ghép tất cả các đoạn bất kể ngắn dài (min_seg_sec=0.0)
                    concat_wav = concat_speaker_segments(wav, segs, max_total_sec=25.0, min_seg_sec=0.0)
                
                if concat_wav is not None:
                    from voice_app.audio_utils import get_duration
                    dur = get_duration(concat_wav)
                    files_list.append({"wav_path": concat_wav, "start": 0.0, "end": dur})
                else:
                    # Fallback cuối cùng nếu ffmpeg lỗi
                    files_list.append({"wav_path": wav, "start": 0.0, "end": 5.0})
                spk_list.append(spk)
                
            update_progress(100, "Đã dịch xong văn bản!", 25, f"Đang trích xuất đặc trưng giọng nói cho {len(spk_list)} người...")
            
            try:
                from voice_app.speaker_manager import _extract_embeddings_from_files_remote
                emb_results = _extract_embeddings_from_files_remote(files_list, task="phân tích hội thoại")
                for idx, emb in enumerate(emb_results):
                    if emb is not None:
                        spk_embeddings[spk_list[idx]] = emb
            except Exception as e:
                print(f"Lỗi extract embeddings remote API: {e}")
                
            # Cleanup temp wavs
            for item in files_list:
                if item["wav_path"] != wav and os.path.exists(item["wav_path"]):
                    with suppress(FileNotFoundError):
                        os.remove(item["wav_path"])

            update_progress(100, "Đã dịch xong văn bản!", 95, "Đang đối chiếu dữ liệu nhân sự...")
            # Greedy assignment: score cao nhất được xử lý trước.
            allowed = json.loads(filter_speakers) if filter_speakers else None
    
            speaker_aliases = _get_speaker_alias_map()

            # Mỗi speaker nhận top-1 nếu đạt ngưỡng chung; không xét gap top-2.
            spk_ranked = {}  # speaker_id -> [(name, score, email, user_info), ...]
            for spk, emb in spk_embeddings.items():
                top_match, ranked_all = _top_db_match(
                    spk_db,
                    emb,
                    allowed_names=allowed,
                    aliases=speaker_aliases,
                )
                spk_ranked[spk] = [top_match] if top_match else []
                ranked_preview = ", ".join(f"{name}={score:.3f}" for name, score, _email, _user_info in ranked_all[:5])
                _append_stt_parse_log(
                    "Voice Meeting",
                    meeting_name,
                    f"[Speaker] {spk}: accepted={bool(top_match)}"
                    + (f" | {ranked_preview}" if ranked_preview else ""),
                )
    
            is_single_chunk = not any(spk.startswith("c") and "_" in spk for spk in spk_embeddings)
            spk_identified = {}

            # Greedy: sắp xếp tất cả (spk, name, score) theo score giảm dần
            all_candidates = []
            for spk, ranked in spk_ranked.items():
                for name, score, email, user_info in ranked:
                    all_candidates.append((score, spk, name, email, user_info))
            all_candidates.sort(key=lambda x: x[0], reverse=True)
    
            claimed_names_by_chunk = {}   # chunk_prefix -> {name: spk}
            claimed_spks  = set()  # spk đã được gán tên
    
            for score, spk, name, email, user_info in all_candidates:
                if spk in claimed_spks:
                    continue  # speaker này đã có tên rồi
                
                chunk_prefix = "all"
                if spk.startswith("c") and "_" in spk:
                    import re
                    m = re.match(r'(c\d+(?:_resume\d*)*)_', spk)
                    if m:
                        chunk_prefix = m.group(1)

                if chunk_prefix not in claimed_names_by_chunk:
                    claimed_names_by_chunk[chunk_prefix] = {}

                # Bỏ ràng buộc CỐT LÕI cũ: cho phép nhiều speaker trong cùng chunk nhận cùng 1 name
                # vì Gemini STT có thể tự cắt 1 người thành nhiều speaker ID khác nhau.
                claimed_names_by_chunk[chunk_prefix][name] = spk
                claimed_spks.add(spk)
                spk_identified[spk] = (name, score, email, user_info)
    
            # Các speaker không match được tên nào → Speaker
            for spk in spk_embeddings:
                if spk not in spk_identified:
                    best_score = spk_ranked[spk][0][1] if spk_ranked.get(spk) else 0.0
                    spk_identified[spk] = ("Speaker", best_score, "", None)
            for spk in unique_speakers:
                if spk not in spk_identified:
                    spk_identified[spk] = ("Speaker", 0.0, "", None)

            # Second pass: trước khi gom "Speaker" giữa các chunk, thử so lại
            # với toàn bộ Voice Speaker DB. Pass đầu có thể bị giới hạn bởi
            # filter_speakers/attendee list, còn pass này giúp nhận ra người đã
            # enroll nhưng không nằm trong danh sách chọn ban đầu.
            rematched_strangers = []
            for spk, info in list(spk_identified.items()):
                if info[0] != "Speaker" or spk not in spk_embeddings:
                    continue
                top_match, _ranked = _top_db_match(
                    spk_db,
                    spk_embeddings[spk],
                    aliases=speaker_aliases,
                )
                if not top_match:
                    continue
                name, score, email, user_info = top_match
                spk_identified[spk] = (name, score, email, user_info)
                rematched_strangers.append(f"{spk}→'{name}'({score:.3f})")
            if rematched_strangers:
                _append_stt_parse_log(
                    "Voice Meeting",
                    meeting_name,
                    "[Speaker] Stranger DB rematch before merge: " + ", ".join(rematched_strangers),
                )
    
            # ── Ưu tiên kết quả gom cụm giọng (không dùng timestamp) ─────────
            # Phần greedy phía trên lấy mẫu giọng bằng cách cắt audio theo
            # start/end của từng segment. Mốc đó do Gemini đoán hoặc
            # forced-align suy ra, đo thực tế trên file 80 phút thì lệch tới
            # hàng trăm giây — cắt trúng lời người khác, mẫu giọng bị lai, rồi
            # hai speaker_id cùng nhận một tên và người còn lại biến mất khỏi
            # biên bản. Gom cụm theo VAD không đụng tới timestamp nên không
            # dính lỗi đó, và ràng buộc 1-1 khiến mỗi người chỉ về một nhóm.
            # Chỉ ghi đè khi nó đủ cơ sở kết luận, còn lại giữ nguyên cách cũ.
            try:
                from voice_app.speaker_manager import identify_speakers_by_voice_clustering

                clustered = identify_speakers_by_voice_clustering(
                    wav,
                    segments,
                    spk_db,
                    task="Nhận diện người nói bằng gom cụm giọng",
                    log_cb=lambda message: _append_stt_parse_log("Voice Meeting", meeting_name, message),
                )
            except Exception as exc:
                clustered = {}
                _append_stt_parse_log("Voice Meeting", meeting_name, f"[VoiceCluster] lỗi: {exc!r}")

            if clustered:
                previous = {spk: info[0] for spk, info in spk_identified.items()}
                for spk in list(spk_identified.keys()) + list(unique_speakers.keys()):
                    # Speaker nào gom cụm không kết luận được thì để Speaker,
                    # không giữ lại tên do cách cũ đoán.
                    spk_identified[spk] = clustered.get(spk) or ("Speaker", 0.0, "", None)
                changed = [
                    f"{spk}: {previous.get(spk)}→{spk_identified[spk][0]}"
                    for spk in spk_identified
                    if previous.get(spk) != spk_identified[spk][0]
                ]
                _append_stt_parse_log(
                    "Voice Meeting",
                    meeting_name,
                    f"[VoiceCluster] áp dụng cho {len(clustered)} speaker"
                    + (f"; đổi: {', '.join(changed)}" if changed else "; trùng kết quả cũ"),
                )
            else:
                # Không đủ cơ sở kết luận. Trả nguyên transcript, để Speaker
                # hết — tên do cách cũ đoán ra không đáng tin (nó lấy mẫu giọng
                # theo timestamp, mà timestamp chính là chỗ đang sai), gán bừa
                # vào biên bản còn tệ hơn là không gán.
                for spk in list(spk_identified.keys()) + list(unique_speakers.keys()):
                    spk_identified[spk] = ("Speaker", 0.0, "", None)
                _append_stt_parse_log(
                    "Voice Meeting",
                    meeting_name,
                    "[VoiceCluster] không đủ cơ sở — giữ transcript thô, tất cả để Speaker.",
                )

            # Log kết quả greedy assignment
            summary = ", ".join(f"{spk}→'{info[0]}'({info[1]:.3f})" for spk, info in spk_identified.items())
            print(f"[Speaker] Greedy result ({len(spk_identified)} speakers): {summary}")
            _append_stt_parse_log("Voice Meeting", meeting_name, f"[Speaker] Greedy result ({len(spk_identified)} speakers): {summary}")
    
            # Không tự merge các "Speaker" giữa chunk.
            # Mỗi speaker_id chưa match DB sẽ giữ thành một nhóm riêng để user
            # dễ nhìn sai/đúng và dùng nút "Quét lại AI" enroll thủ công.
            strangers = [spk for spk, info in spk_identified.items() if info[0] == "Speaker"]
            groups = [[spk] for spk in strangers]
            stranger_groups = {spk: spk for spk in strangers}
            if strangers:
                _append_stt_parse_log(
                    "Voice Meeting",
                    meeting_name,
                    f"[Speaker] Stranger merge disabled; kept {len(strangers)} unknown speaker ids separate.",
                )
    
            # Đánh số "Speaker N" theo thứ tự xuất hiện
            group_label = {}  # group_id -> "Unknown_Group_X"
            for spk in strangers:
                group_id = stranger_groups.get(spk, spk)
                if group_id not in group_label:
                    group_label[group_id] = f"Unknown_Group_{group_id}"
    
            # Tạo speaker_cache với nhãn hiển thị sạch
            speaker_cache = {}
            for spk, info in spk_identified.items():
                name, score, email, user_info = info
                if name != "Speaker":
                    if not email or email.lower() == "chưa cập nhật":
                        speaker_cache[spk] = f"👤 {name}"
                    else:
                        speaker_cache[spk] = f"👤 {name} ({email})"
                else:
                    group_id = stranger_groups.get(spk, spk)
                    label = group_label.get(group_id, f"Unknown_Group_{group_id}")
                    speaker_cache[spk] = f"👤 {label}"
    
            # Fallback cho những spk không có embedding
            for spk in unique_speakers:
                if spk not in speaker_cache:
                    speaker_cache[spk] = f"👤 Unknown_Group_Fallback_{spk}"
    
            # ── LỌC SEGMENT VÔ NGHĨA ──────────────────────────────────────────────
            def is_meaningful(text):
                """
                Lọc các segment rác/ngắn để transcript sạch hơn, nhưng phần
                timeline của các segment còn lại vẫn phải giữ nguyên.
                """
                import re
                t = text.strip()
                # Loại bỏ các dấu ... ở đầu và cuối để dễ check
                t_clean = re.sub(r'^(?:\.{2,}\s*)|(?:\s*\.{2,})$', '', t).strip()
                
                if not t_clean:
                    return False
                # Loại bỏ câu chỉ có dấu câu / ký tự đặc biệt
                if re.fullmatch(r'[\W\d]+', t_clean):
                    return False

                t_lower = " ".join(t_clean.lower().split())
                hallucinations = {
                    "xong rồi gì nữa",
                    "em xích lên cho",
                    "cảm ơn các bạn",
                    "xin chào",
                    "tạm biệt",
                    "cảm ơn",
                    "hết",
                    "chào các bạn",
                }
                if t_lower in hallucinations and len(t_clean.split()) <= 5:
                    return False

                return True
    
            # ── GỘP SEGMENT LIỀN KỀ CÙNG SPEAKER ─────────────────────────────────
            # Gán embedding đại diện của cụm cho từng segment
            for seg in segments:
                spk = seg["speaker_id"]
                if spk in spk_embeddings:
                    emb_np = spk_embeddings[spk]
                    norm = np.linalg.norm(emb_np)
                    if norm > 0: emb_np = emb_np / norm
                    seg["embedding"] = emb_np.tolist()

            # Nếu 2 segment liên tiếp của CÙNG 1 speaker và khoảng ngắt nghỉ <= 1.5s → gộp lại
            MERGE_GAP = 1.5  # giây
    
            merged_segments = []
            omitted_segment_barrier = False
            if stt_mode == "google":
                segments.sort(key=lambda x: x["start"])

            actual_stranger_counter = 1
            real_stranger_map = {}

            for seg in segments:
                import re
                txt = " ".join(seg["text"].split())
                # Dọn dẹp tất cả dấu "..." hoặc ".." rác trong câu
                txt = re.sub(r'\.{2,}', ' ', txt)
                txt = " ".join(txt.split()).strip()
                
                if not txt or not _is_meaningful_transcript_text(txt):
                    omitted_segment_barrier = True
                    continue
                
                spk_cache_val = speaker_cache.get(seg["speaker_id"], seg["speaker_id"]).strip()
                clean_spk = spk_cache_val.replace("👤 ", "")
                
                if clean_spk.startswith("Unknown_Group_"):
                    if clean_spk not in real_stranger_map:
                        real_stranger_map[clean_spk] = f"Speaker {actual_stranger_counter}"
                        actual_stranger_counter += 1
                    spk_label = f"👤 {real_stranger_map[clean_spk]}"
                else:
                    spk_label = spk_cache_val
                    if not spk_label.startswith("👤 "):
                        spk_label = f"👤 {spk_label}"
                        
                spk_label = " ".join(spk_label.split())
                emb = seg.get("embedding")
                raw_spk_id = seg.get("speaker_id", "")

                if (
                        merged_segments
                        and not omitted_segment_barrier
                        and merged_segments[-1][2] == spk_label
                        and len(merged_segments[-1]) > 5
                        and merged_segments[-1][5] == raw_spk_id
                        and seg["start"] - merged_segments[-1][1] <= MERGE_GAP
                ):
                    # Gộp vào segment trước của CÙNG 1 người nói gốc
                    prev_s, prev_e, prev_spk, prev_txt, prev_emb, _prev_raw = merged_segments[-1]
                    merged_segments[-1] = (prev_s, seg["end"], prev_spk, prev_txt + " " + txt, prev_emb if prev_emb is not None else emb, raw_spk_id)
                else:
                    merged_segments.append((seg["start"], seg["end"], spk_label, txt, emb, raw_spk_id))
                omitted_segment_barrier = False

            def collapse_short_stranger_labels(items):
                from collections import defaultdict

                stats = defaultdict(lambda: {"segments": 0, "duration": 0.0})
                for row in items:
                    s, e, label, _txt, _emb = row[:5]
                    stats[label]["segments"] += 1
                    stats[label]["duration"] += max(0.0, float(e or s) - float(s or 0))

                def is_short_stranger(label):
                    item = stats[label]
                    # "Người lạ" là nhãn của các bản ghi cũ, vẫn phải nhận ra.
                    if not str(label).startswith(("👤 Speaker", "👤 Người lạ")):
                        return False
                    if item["duration"] <= 3.0:
                        return True
                    return item["duration"] <= 8.0 and item["segments"] <= 3

                short_labels = {label for label in stats if is_short_stranger(label)}
                if not short_labels:
                    return items

                remap = {}
                for idx, row in enumerate(items):
                    s, e, label = row[0], row[1], row[2]
                    if label not in short_labels:
                        continue
                    best_label = None
                    best_distance = None
                    for direction in (-1, 1):
                        j = idx + direction
                        while 0 <= j < len(items):
                            candidate = items[j][2]
                            if candidate != label and candidate not in short_labels:
                                if direction < 0:
                                    distance = abs(float(s or 0) - float(items[j][1] or items[j][0] or 0))
                                else:
                                    distance = abs(float(items[j][0] or 0) - float(e or s or 0))
                                if best_distance is None or distance < best_distance:
                                    best_distance = distance
                                    best_label = candidate
                                break
                            j += direction
                    if best_label:
                        remap[label] = best_label

                if not remap:
                    return items

                print(f"[LABEL CLEANUP] Short stranger remap: {remap}")
                frappe.logger("voice_app").error(f"[LABEL CLEANUP] Short stranger remap: {remap}")

                cleaned = []
                for row in items:
                    s, e, label, txt, emb = row[:5]
                    raw_spk_id = row[5] if len(row) > 5 else ""
                    new_label = remap.get(label, label)
                    if cleaned and cleaned[-1][2] == new_label and len(cleaned[-1]) > 5 and cleaned[-1][5] == raw_spk_id and s - cleaned[-1][1] <= 1.5:
                        prev_s, prev_e, prev_label, prev_txt, prev_emb, _prev_raw = cleaned[-1]
                        cleaned[-1] = (prev_s, e, prev_label, prev_txt + " " + txt, prev_emb if prev_emb is not None else emb, raw_spk_id)
                    else:
                        cleaned.append((s, e, new_label, txt, emb, raw_spk_id))
                return cleaned

            def renumber_stranger_labels(items):
                import re

                remap = {}
                next_idx = 1
                renumbered = []
                for row in items:
                    s, e, label, txt, emb = row[:5]
                    raw_spk_id = row[5] if len(row) > 5 else ""
                    if re.match(r"^👤 (?:Speaker|Người lạ) \d+$", str(label)):
                        if label not in remap:
                            remap[label] = f"👤 Speaker {next_idx}"
                            next_idx += 1
                        label = remap[label]
                    renumbered.append((s, e, label, txt, emb, raw_spk_id))
                return renumbered

            merged_segments = renumber_stranger_labels(merged_segments)

            # Format results
            ui_results = []
            original_results = []
            for row in merged_segments:
                s, e, spk_label, txt, emb = row[:5]
                raw_spk_id = row[5] if len(row) > 5 else ""
                ui_results.append((s, e, spk_label, txt))
                original_results.append({
                    "start": s,
                    "end": e,
                    "speaker": spk_label,
                    "text": txt,
                    "embedding": emb,
                    "speaker_id": raw_spk_id
                })

            final_output_text = ""
            last_spk = None

            for s, e, spk_label, txt in ui_results:
                if spk_label != last_spk:
                    final_output_text += f"\n**{spk_label}** [{s:.1f}s]\n{txt}"
                else:
                    final_output_text += f" {txt}"
                last_spk = spk_label

            # Cleanup temp wav
            if os.path.exists(wav): os.remove(wav)
    
            raw_employees = get_cached_employees()
            employees = [e for e in raw_employees if e.get("user_id")]

            # Update Voice Meeting
            frappe.db.set_value("Voice Meeting", meeting_name, {
                "status": "Completed",
                "transcript": final_output_text.strip(),
                "raw_results": json.dumps(ui_results, ensure_ascii=False),
                "original_raw_results": json.dumps(original_results, ensure_ascii=False)
            })
            frappe.db.commit()
    
            # Log AI call (Gemini STT)
            try:
                session_name = frappe.db.get_value("VOICE Session", {"session_id": session_id_header}, "name") if session_id_header else ""
                if session_name:
                    ai_model_log = "google/gemini"
                    action_name = _logger.start_action(session_name, action_type="transcribe_audio", input_summary=f"Transcribe with {stt_label}")
                    if stt_mode == "google":
                        _logger.log_ai_call(
                            session_name=session_name,
                            action_name=action_name,
                            call_type="transcribe_audio",
                            ai_model=ai_model_log,
                            duration_seconds=0,
                            status="success",
                            prompt_tokens=el_chars_used,
                            completion_tokens=el_chars_remaining,
                        )
                        _logger.finish_action(
                            action_name, status="success",
                            prompt_tokens=el_chars_used,
                            completion_tokens=el_chars_remaining,
                        )
                    else:
                        _logger.log_ai_call(
                            session_name=session_name,
                            action_name=action_name,
                            call_type="transcribe_audio",
                            ai_model=ai_model_log,
                            duration_seconds=0,
                            status="success",
                            elevenlabs_chars_used=el_chars_used,
                            elevenlabs_chars_remaining=el_chars_remaining,
                        )
                        _logger.finish_action(action_name, status="success")
            except Exception as log_ex:
                if getattr(frappe.db, "_cursor", None):
                    frappe.db._cursor.execute("ROLLBACK")
                frappe.db.rollback()
                frappe.log_error(str(log_ex), "Log Gemini STT AI Call Error")
    
            result_data = {
                "status": "success",
                "results": ui_results,
                "final_text": final_output_text.strip(),
                "employees": employees,
                "meeting_name": meeting_name
            }
            frappe.publish_realtime("transcribe_result", result_data, after_commit=False)
            return result_data
    
        except Exception as e:
            if getattr(frappe.db, "_cursor", None):
                frappe.db._cursor.execute("ROLLBACK")
            frappe.db.rollback()
            frappe.log_error(traceback.format_exc(), "Audio Transcription Error")
            frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": str(e)})
            frappe.db.commit()
            frappe.publish_realtime("transcribe_result", {"status": "error", "message": str(e), "meeting_name": meeting_name}, after_commit=False)
            return
    
    
    
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Transcribe Async Error")
        frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Error", "error_message": str(e)})
        frappe.db.commit()

@frappe.whitelist(allow_guest=False)
def extract_tasks():
    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    if not meeting_name:
        return {"status": "error", "message": "Thiếu meeting_name"}

    session_id_header = frappe.request.headers.get("X-App-Session-Id", "")
    frappe.enqueue(
        "voice_app.api._extract_tasks_async",
        queue="long",
        timeout=1500,
        payload=payload,
        user=frappe.session.user,
        session_id_header=session_id_header
    )
    return {"status": "processing"}

@frappe.whitelist(allow_guest=False)
def check_extract_status(meeting_name):
    # Dùng frappe.cache()
    key = f"extract_result_{meeting_name}"
    result = frappe.cache().get_value(key)
    if result:
        frappe.cache().delete_value(key)
        return result
    return {"status": "processing"}

def _extract_tasks_async(payload, user, session_id_header):
    frappe.session.user = user
    results = payload.get("results", [])
    model_type = payload.get("model_type", "gpt-4o")
    meeting_name = payload.get("meeting_name")
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    location = payload.get("location")
    chairperson = payload.get("chairperson")

    if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
        if location:
            frappe.db.set_value("Voice Meeting", meeting_name, "location", location)
        else:
            location = frappe.db.get_value("Voice Meeting", meeting_name, "location")
            
        if chairperson:
            frappe.db.set_value("Voice Meeting", meeting_name, "chairperson", chairperson)
        else:
            chairperson = frappe.db.get_value("Voice Meeting", meeting_name, "chairperson")

        if not start_time:
            meeting_date = frappe.db.get_value("Voice Meeting", meeting_name, "date")
            if meeting_date:
                # Format datetime if it is a datetime object
                if hasattr(meeting_date, "strftime"):
                    start_time = meeting_date.strftime("%d/%m/%Y %H:%M:%S")
                else:
                    start_time = str(meeting_date)

    cache_key = f"extract_result_{meeting_name}"

    if not results and meeting_name:
        try:
            # Check if it's the primary key
            raw_results = frappe.db.get_value("Voice Meeting", meeting_name, "raw_results")
            if not raw_results:
                # Fallback to searching by title
                doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
                if doc_name:
                    meeting_name = doc_name
                    raw_results = frappe.db.get_value("Voice Meeting", doc_name, "raw_results")
            
            if raw_results:
                results = json.loads(raw_results)
        except (TypeError, json.JSONDecodeError) as exc:
            frappe.log_error(str(exc), "Parse Meeting Results For Task Error")

    if not results:
        frappe.cache().set_value(cache_key, {"status": "error", "message": "Không có nội dung để tạo task"}, expires_in_sec=86400)
        return

    try:
        from voice_app.constants import get_worksuite_url, get_worksuite_token
        speaker_roles = {}
        try:
            voice_speakers = frappe.get_all(
                "Voice Speaker",
                fields=["speaker_name", "email"],
            )
            spk_email_map = {s["speaker_name"]: s["email"] for s in voice_speakers if s.get("email")}

            if True:
                data = get_cached_employees()
                if data:
                    email_desg_map = {
                        e["user_id"]: e["designation"]
                        for e in data
                        if e.get("user_id") and e.get("designation")
                    }
                    name_desg_map = {
                        e["employee_name"]: e["designation"]
                        for e in data
                        if e.get("employee_name") and e.get("designation")
                    }
                    for spk_name, email in spk_email_map.items():
                        if email in email_desg_map:
                            speaker_roles[spk_name] = email_desg_map[email]
                    
                    for emp_name, desg in name_desg_map.items():
                        speaker_roles[emp_name] = desg
                        speaker_roles[emp_name.strip().lower()] = desg
                        alt_name_1 = emp_name.replace('úy', 'uý').replace('ủy', 'uỷ').replace('ũy', 'uỹ').replace('ụy', 'uỵ').replace('ùy', 'uỳ')
                        alt_name_2 = emp_name.replace('uý', 'úy').replace('uỷ', 'ủy').replace('uỹ', 'ũy').replace('uỵ', 'ụy').replace('uỳ', 'ùy')
                        speaker_roles[alt_name_1] = desg
                        speaker_roles[alt_name_1.strip().lower()] = desg
                        speaker_roles[alt_name_2] = desg
                        speaker_roles[alt_name_2.strip().lower()] = desg

        except Exception as re_ex:
            if hasattr(frappe.db, 'rollback'): frappe.db.rollback()
            frappe.log_error(str(re_ex), "Fetch Designations Error")

        docx_filename = save_to_docx(
            results, 
            speaker_roles=speaker_roles,
            start_time=start_time,
            end_time=end_time,
            location=location,
            chairperson=chairperson
        )
        
        with open(docx_filename, "rb") as f:
            if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
                file_doc = save_file(docx_filename, f.read(), "Voice Meeting", meeting_name, is_private=0)
                file_doc = _ensure_file_attachment(file_doc.file_url, "Voice Meeting", meeting_name, file_name=os.path.basename(docx_filename), is_private=0) or file_doc
            else:
                file_doc = save_file(docx_filename, f.read(), None, None, is_private=0)
            docx_url = file_doc.file_url

        items, hr_projects_map, errors, employees, task_usage, meeting_summary, conclusion = extract_tasks_only(docx_filename, model_type="gpt-4o-mini")

        if os.path.exists(docx_filename): os.remove(docx_filename)

        excel_url = ""
        if items:
            df = pd.DataFrame(items)
            df.rename(columns={
                "title": "Tên nhiệm vụ",
                "assignee_display": "Người thực hiện",
                "project": "Dự án",
                "start_date": "Ngày bắt đầu",
                "due_date": "Ngày kết thúc",
                "description": "Mô tả chi tiết"
            }, inplace=True)
            
            if "assignee" in df.columns:
                df.drop(columns=["assignee"], inplace=True)
                
            excel_filename = f"tasks_{os.urandom(2).hex()}.xlsx"
            df.to_excel(excel_filename, index=False)
            
            with open(excel_filename, "rb") as f:
                if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
                    excel_doc = save_file(excel_filename, f.read(), "Voice Meeting", meeting_name, is_private=0)
                    excel_doc = _ensure_file_attachment(excel_doc.file_url, "Voice Meeting", meeting_name, file_name=excel_filename, is_private=0) or excel_doc
                else:
                    excel_doc = save_file(excel_filename, f.read(), None, None, is_private=0)
                excel_url = excel_doc.file_url
            if os.path.exists(excel_filename): os.remove(excel_filename)

        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if _can_access_meeting(meeting_owner, user):
                frappe.db.set_value("Voice Meeting", meeting_name, "minute_docx", docx_url)
                frappe.db.set_value("Voice Meeting", meeting_name, "task_xlsx", excel_url)
                frappe.db.set_value("Voice Meeting", meeting_name, "status", "Analyzed")
                if items:
                    frappe.db.set_value("Voice Meeting", meeting_name, "tasks_json",
                                        json.dumps(items, ensure_ascii=False))
                
                if meeting_summary:
                    frappe.db.set_value("Voice Meeting", meeting_name, "meeting_summary", meeting_summary)
                if conclusion:
                    frappe.db.set_value("Voice Meeting", meeting_name, "conclusion", conclusion)
            else:
                raise frappe.PermissionError("Không có quyền cập nhật meeting này")

        frappe.db.commit()

        try:
            session_name_log = frappe.db.get_value("VOICE Session", {"session_id": session_id_header}, "name") if session_id_header else ""
            if session_name_log and task_usage:
                action_name = _logger.start_action(session_name_log, action_type="extract_tasks", input_summary="Extract tasks from text")
                _logger.log_ai_call(
                    session_name=session_name_log,
                    action_name=action_name,
                    call_type="extract_tasks",
                    ai_model=model_type,
                    duration_seconds=0,
                    status="success",
                    prompt_tokens=task_usage.get("prompt_tokens", 0),
                    completion_tokens=task_usage.get("completion_tokens", 0)
                )
                _logger.finish_action(action_name, status="success")
        except Exception as log_ex:
            frappe.log_error(str(log_ex), "Log OpenAI AI Call Error")

        frappe.cache().set_value(cache_key, {
            "status": "success",
            "items": items,
            "hr_projects_map": hr_projects_map,
            "errors": errors,
            "employees": employees,
            "docx_url": docx_url,
            "excel_url": excel_url,
            "meeting_summary": meeting_summary,
            "conclusion": conclusion
        }, expires_in_sec=86400)

    except Exception as e:
        if hasattr(frappe.db, 'rollback'): frappe.db.rollback()
        frappe.log_error(traceback.format_exc(), "Task Extraction Error")
        frappe.cache().set_value(cache_key, {"status": "error", "message": str(e)}, expires_in_sec=86400)

@frappe.whitelist(allow_guest=False)
def get_employees():
    import requests
    from voice_app.constants import get_worksuite_url, get_worksuite_token

    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    def _local_employee_fallback():
        local = []
        seen = set()
        with suppress(Exception):
            users = frappe.get_all(
                "User",
                filters={"enabled": 1},
                fields=["name", "full_name", "email", "user_type"],
                order_by="full_name asc",
                limit=500,
            )
            for user in users:
                email = (user.get("email") or user.get("name") or "").strip()
                full_name = (user.get("full_name") or "").strip()
                if (
                    not email
                    or email.lower() in {"guest@example.com", "admin@example.com"}
                    or full_name in {"Guest", "Administrator"}
                    or user.get("name") in {"Guest", "Administrator"}
                    or user.get("user_type") == "Website User"
                    or email in seen
                ):
                    continue
                seen.add(email)
                local.append(
                    {
                        "name": email,
                        "employee_name": full_name or email,
                        "user_id": email,
                        "designation": user.get("user_type") or "",
                    }
                )
        with suppress(Exception):
            speakers = frappe.get_all(
                "Voice Speaker",
                fields=["speaker_name", "email"],
                order_by="speaker_name asc",
                limit=500,
            )
            speaker_names = {
                (speaker.get("speaker_name") or "").strip()
                for speaker in speakers
                if (speaker.get("speaker_name") or "").strip()
            }
            speaker_aliases = _build_speaker_alias_map(speakers)
            for speaker in speakers:
                name = (speaker.get("speaker_name") or "").strip()
                email = (speaker.get("email") or "").strip()
                if email == "Chưa cập nhật":
                    email = ""
                if speaker_aliases.get(name, name) != name:
                    continue
                if name.endswith(" - Voice Speaker") and name[: -len(" - Voice Speaker")] in speaker_names:
                    continue
                key = email or name
                if not name or key in seen:
                    continue
                seen.add(key)
                local.append(
                    {
                        "name": key,
                        "employee_name": name,
                        "user_id": email,
                        "designation": "Voice Speaker",
                    }
                )
        return local

    employees = []
    try:
        base_url, token = get_worksuite_url(), get_worksuite_token()
        
        if not base_url or not token:
            return {
                "status": "success",
                "employees": _local_employee_fallback(),
                "source": "local_fallback",
                "message": "Chưa cấu hình Sync API, đang dùng danh sách local.",
            }
            
        if not base_url.startswith("http"):
            base_url = "https://" + base_url
            
        url = f"{base_url.rstrip('/')}/api/method/ct_agent_hub.api.admin.get_admin_users"
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/json"
        }
        data = {
            "page": "1",
            "limit": "9999999999"
        }
        
        response = requests.post(url, headers=headers, data=data, timeout=30)
        
        if response.status_code == 401:
            return {"status": "error", "message": "Xác thực thất bại (401). Token có thể đã hết hạn hoặc không hợp lệ."}
            
        response.raise_for_status()
        resp_json = response.json()
        
        resp_data = resp_json.get("message", {}) if "message" in resp_json else resp_json
        users = resp_data.get("users", [])
        
        for u in users:
            email = (u.get("email") or "").strip()
            if not email:
                continue
                
            full_name = (u.get("full_name") or "").strip()
            job_title = (u.get("job_title") or "").strip()
            
            # departments = u.get("departments") or []
            # dept = str(departments[0]).strip() if departments else ""
            
            # designation = job_title if job_title else dept
            designation = job_title 

            employees.append({
                "name": email,
                "employee_name": full_name,
                "user_id": email,
                "designation": designation
            })

    except requests.RequestException as e:
        frappe.log_error(message=str(e), title="Fetch Employees Error in get_employees")
        return {"status": "error", "message": f"Lỗi khi gọi API hệ thống ngoài: {str(e)}"}
    except Exception as e:
        frappe.log_error(message=str(e), title="Fetch Employees Error in get_employees")
        return {"status": "error", "message": f"Lỗi xử lý dữ liệu đồng bộ: {str(e)}"}
        
    return {"status": "success", "employees": employees}


@frappe.whitelist(allow_guest=False)
def update_meeting_results():
    """Cập nhật raw_results khi user hoàn tác lọc (undo clean)"""
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    results = payload.get("results", [])

    if not meeting_name or not results:
        return {"status": "error", "message": "Thiếu meeting_name hoặc results"}

    try:
        if not frappe.db.exists("Voice Meeting", meeting_name):
            doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
            if doc_name:
                meeting_name = doc_name
                
        if frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if not _can_access_meeting(meeting_owner):
                return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}
            # Gộp lại nội dung text
            final_text = " ".join([seg[3].strip() for seg in results if len(seg) > 3 and seg[3] and seg[3].strip()])
            
            frappe.db.set_value("Voice Meeting", meeting_name, "raw_results",
                                json.dumps(results, ensure_ascii=False))
            frappe.db.set_value("Voice Meeting", meeting_name, "transcript", final_text)
            frappe.db.commit()
        return {"status": "success"}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Update Meeting Results Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def update_transcript_text():
    """Cập nhật nội dung transcript khi user chỉnh sửa thủ công"""
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    results = payload.get("results", [])

    if not meeting_name or not results:
        return {"status": "error", "message": "Thiếu meeting_name hoặc results"}

    try:
        if not frappe.db.exists("Voice Meeting", meeting_name):
            doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
            if doc_name:
                meeting_name = doc_name
                
        if frappe.db.exists("Voice Meeting", meeting_name):
            meeting_owner = frappe.db.get_value("Voice Meeting", meeting_name, "owner")
            if not _can_access_meeting(meeting_owner):
                return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}
            
            # Gộp lại nội dung text
            final_text = " ".join([seg[3].strip() for seg in results if len(seg) > 3 and seg[3] and seg[3].strip()])
            
            frappe.db.set_value("Voice Meeting", meeting_name, "raw_results",
                                json.dumps(results, ensure_ascii=False))
            frappe.db.set_value("Voice Meeting", meeting_name, "transcript", final_text)
            frappe.db.commit()
        return {"status": "success", "final_text": final_text}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Update Transcript Error")

@frappe.whitelist(allow_guest=False)
def sync_tasks_to_erp():
    data = frappe.request.get_data()
    payload = json.loads(data)
    tasks = payload.get("tasks", [])

    if not tasks:
        return {"status": "error", "message": "Không có task nào để đẩy"}

    try:
        report = create_tasks_to_erp(tasks)
        return {"status": "success", "report": report}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "ERP Sync Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def download_meeting_file():
    """
    Endpoint tải file (docx/xlsx) từ meeting về phía client.
    Chỉ cho phép chủ sở hữu cuộc họp tải.
    Params: meeting_name, file_type (docx | xlsx)
    """
    if frappe.session.user == "Guest":
        frappe.throw("Vui lòng đăng nhập để tải file", frappe.AuthenticationError)

    meeting_name = frappe.form_dict.get("meeting_name") or frappe.local.form_dict.get("meeting_name")
    file_type    = frappe.form_dict.get("file_type")    or frappe.local.form_dict.get("file_type", "docx")

    if not meeting_name or not file_type:
        frappe.throw("Thiếu tham số meeting_name hoặc file_type")

    if not frappe.db.exists("Voice Meeting", meeting_name):
        doc_name = frappe.db.get_value("Voice Meeting", {"title": meeting_name, "owner": frappe.session.user}, "name")
        if doc_name:
            meeting_name = doc_name

    if not frappe.db.exists("Voice Meeting", meeting_name):
        frappe.throw("Meeting không tồn tại")
        
    meeting = frappe.get_doc("Voice Meeting", meeting_name)

    # Kiểm tra chủ sở hữu
    if meeting.owner != frappe.session.user:
        frappe.throw("Bạn không có quyền tải file này", frappe.PermissionError)

    if file_type == "xlsx":
        file_url = meeting.task_xlsx
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        file_url = meeting.minute_docx
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"

    if not file_url:
        frappe.throw(f"Meeting chưa có file {ext.upper()}")

    # Resolve đường dẫn đúng theo quy tắc Frappe:
    # - Public  (/files/xxx)          → {site_path}/public/files/xxx
    # - Private (/private/files/xxx)  → {site_path}/private/files/xxx
    clean_url = file_url.lstrip("/")
    if clean_url.startswith("files/"):
        # Public file — cần thêm tiền tố "public/"
        file_path = frappe.get_site_path("public", clean_url)
    else:
        # Private file hoặc đường dẫn đã đầy đủ
        file_path = frappe.get_site_path(clean_url)

    if not os.path.exists(file_path):
        frappe.throw(f"File không tồn tại trên server: {file_url} → {file_path}")


    # Tên file tải xuống = title của meeting
    safe_title = meeting.title.replace("/", "-").replace("\\", "-")
    filename   = f"{safe_title}.{ext}"

    with open(file_path, "rb") as f:
        file_content = f.read()

    frappe.local.response.filename    = filename
    frappe.local.response.filecontent = file_content
    frappe.local.response.type        = "download"
    frappe.local.response["content_type"] = content_type




@frappe.whitelist(allow_guest=False)
def get_elevenlabs_info():
    return {"balance": "ElevenLabs STT đã tắt. Hệ thống đang dùng Google Gemini."}

@frappe.whitelist(allow_guest=False)
def enroll_voice():
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập để đăng ký giọng nói."}
        
    email = frappe.session.user
    full_name = frappe.utils.get_fullname(email)
    user_info = None

    if 'file' not in frappe.request.files:
        return {"status": "error", "message": "Thiếu file âm thanh"}
        
    audio_file = frappe.request.files['file']
    
    # Save uploaded file
    file_doc = save_file(audio_file.filename, audio_file.read(), None, None, is_private=1)
    file_path = frappe.get_site_path(file_doc.file_url.strip('/'))
    
    try:
        # Convert to WAV
        wav, err = convert_to_wav(file_path)
        if err:
            return {"status": "error", "message": err}
            
        from voice_app.api import get_cached_employees
        employees = get_cached_employees()
        designation = ""
        for emp in employees:
            if emp.get("user_id") == email:
                full_name = emp.get("employee_name") or full_name
                designation = emp.get("designation") or ""
                break
                
        speaker_name = full_name or email
        
        from voice_app.speaker_manager import enroll_new_speaker
        success = enroll_new_speaker(speaker_name, wav, email=email, user_info=user_info)
        
        # Cleanup temp wav
        if os.path.exists(wav): os.remove(wav)
        
        if success:
            return {"status": "success", "message": f"Đã đăng ký giọng nói thành công cho {full_name}!"}
        else:
            return {"status": "error", "message": "Không thể trích xuất đặc trưng giọng nói."}
            
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Voice Enrollment Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=False)
def map_and_enroll_speakers():
    """
    Gán nhiều nhãn người lạ, enroll các mẫu giọng còn thiếu, rồi quét lại
    toàn bộ transcript đúng một lần bằng Voice Speaker DB.
    """
    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    speaker_aliases = _get_speaker_alias_map()
    mappings = {
        str(old).strip(): _normalize_requested_speaker_name(new, speaker_aliases)
        for old, new in (payload.get("mappings", {}) or {}).items()
        if str(old).strip() and str(new).strip()
    }
    
    if not meeting_name or not mappings:
        return {"status": "error", "message": "Thiếu dữ liệu meeting_name hoặc mappings"}
        
    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not meeting or not meeting.raw_results:
        return {"status": "error", "message": "Không tìm thấy meeting hoặc dữ liệu raw_results"}
    if not _can_access_meeting(meeting.owner):
        return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}

    results = json.loads(meeting.raw_results)
    original_results = json.loads(meeting.original_raw_results) if meeting.original_raw_results else []

    def _seg_get(seg, key, idx=None, default=None):
        if isinstance(seg, dict):
            return seg.get(key, default)
        if idx is not None and len(seg) > idx:
            return seg[idx]
        return default

    def _seg_set_speaker(seg, value):
        if isinstance(seg, dict):
            seg["speaker"] = value
        elif len(seg) > 2:
            seg[2] = value

    def _seg_set_embedding(seg, value):
        emb_list = value.tolist() if hasattr(value, "tolist") else value
        if isinstance(seg, dict):
            seg["embedding"] = emb_list
        elif len(seg) > 4:
            seg[4] = emb_list
        else:
            while len(seg) < 4:
                seg.append("")
            seg.append(emb_list)

    def _has_embedding(emb):
        if emb is None:
            return False
        if isinstance(emb, (list, tuple)) and not emb:
            return False
        return True

    def _normalize_embedding(emb):
        import numpy as np

        if emb is None:
            return None
        emb_np = np.array(emb, dtype=np.float32)
        norm = np.linalg.norm(emb_np)
        if norm > 0:
            emb_np = emb_np / norm
        return emb_np

    def _is_unknown_label(label, known_names):
        text = str(label or "").strip()
        if not text:
            return True
        if any(marker in text for marker in ("Speaker", "Người lạ", "Unknown", "Không tên")):
            return True
        return text not in known_names

    def _audio_file_path(file_url):
        clean_url = (file_url or "").lstrip("/")
        if not clean_url:
            return ""
        if clean_url.startswith("files/"):
            return frappe.get_site_path("public", clean_url)
        return frappe.get_site_path(clean_url)

    def _duration(seg):
        start = float(_seg_get(seg, "start", 0, 0) or 0)
        end = float(_seg_get(seg, "end", 1, start) or start)
        return max(0.0, end - start)

    if not original_results:
        original_results = [
            {
                "start": _seg_get(seg, "start", 0, 0),
                "end": _seg_get(seg, "end", 1, 0),
                "speaker": _seg_get(seg, "speaker", 2, ""),
                "text": _seg_get(seg, "text", 3, ""),
                "embedding": _seg_get(seg, "embedding", 4, None),
            }
            for seg in results
        ]

    enrolled = []
    skipped = []
    errors = []
    db = SpeakerDB()
    manual_assignments = _build_manual_speaker_assignments(results, original_results, mappings)

    sample_indexes = {}
    for old_speaker, new_speaker in mappings.items():
        best_idx = None
        best_dur = 0
        for i, seg in enumerate(results):
            if _seg_get(seg, "speaker", 2, "") != old_speaker:
                continue
            dur = _duration(seg)
            if dur > best_dur:
                best_idx = i
                best_dur = dur
        if best_idx is None or best_dur < 2.0:
            errors.append(f"{new_speaker} (Audio quá ngắn, cần > 2s)")
            continue
        current = frappe.get_all("Voice Speaker", filters={"speaker_name": new_speaker}, fields=["name", "embedding"])
        if current and current[0].get("embedding"):
            skipped.append(new_speaker)
        else:
            sample_indexes[new_speaker] = best_idx

    wav_path = ""
    try:
        from voice_app.speaker_manager import _extract_embeddings_from_files_remote

        def _ensure_wav():
            nonlocal wav_path
            if wav_path:
                return wav_path
            audio_path = _audio_file_path(meeting.audio_file)
            if not audio_path or not os.path.exists(audio_path):
                raise RuntimeError("Không tìm thấy file âm thanh gốc để trích xuất giọng nói.")
            wav_path, err = convert_to_wav(audio_path)
            if err:
                raise RuntimeError(f"Lỗi xử lý file âm thanh: {err}")
            return wav_path

        segment_embedding_rebuild = _rebuild_segment_embeddings_from_audio(
            meeting,
            original_results,
            force=True,
            min_duration=0.8,
            task="Rebuild từng segment khi quét lại nhiều speaker",
        )
        if segment_embedding_rebuild.get("error"):
            return {"status": "error", "message": segment_embedding_rebuild["error"]}

        missing_samples = []
        missing_sample_names = []
        for new_speaker, idx in sample_indexes.items():
            seg = original_results[idx] if idx < len(original_results) else results[idx]
            emb = _seg_get(seg, "embedding", 4, None)
            if _has_embedding(emb):
                continue
            start = float(_seg_get(seg, "start", 0, 0) or 0)
            end = float(_seg_get(seg, "end", 1, start) or start)
            missing_sample_names.append(new_speaker)
            missing_samples.append({"wav_path": _ensure_wav(), "start": start, "end": end})
        if missing_samples:
            emb_results = _extract_embeddings_from_files_remote(missing_samples, task="Đăng ký nhiều giọng nói")
            for new_speaker, emb in zip(missing_sample_names, emb_results):
                idx = sample_indexes[new_speaker]
                if emb is not None and idx < len(original_results):
                    _seg_set_embedding(original_results[idx], emb)

        for new_speaker, idx in sample_indexes.items():
            seg = original_results[idx] if idx < len(original_results) else results[idx]
            emb = _seg_get(seg, "embedding", 4, None)
            if not _has_embedding(emb):
                errors.append(f"{new_speaker} (Không trích được embedding)")
                continue
            start = float(_seg_get(seg, "start", 0, 0) or 0)
            end = float(_seg_get(seg, "end", 1, start) or start)
            clean_sample = _clean_speaker_sample_embedding(_ensure_wav(), start, end, fallback_embedding=emb, task="Lọc sample khi đăng ký nhiều giọng")
            clean_emb = clean_sample.get("embedding")
            if clean_emb is None:
                clean_emb = _normalize_embedding(emb)
            db.add_speaker(new_speaker, clean_emb, email="", user_info=None)
            enrolled.append(new_speaker)

            if frappe.db.has_column("Voice Speaker", "sample_audio"):
                with suppress(Exception):
                    from voice_app.audio_utils import extract_segment_ffmpeg

                    sample_path = extract_segment_ffmpeg(_ensure_wav(), clean_sample.get("start") or start, clean_sample.get("end") or end, padding=0.1)
                    if sample_path and os.path.exists(sample_path):
                        safe_name = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in new_speaker).strip()
                        with open(sample_path, "rb") as f:
                            file_doc = save_file(f"{safe_name or 'speaker'}_{int(time.time())}.wav", f.read(), "Voice Speaker", new_speaker, is_private=1)
                        frappe.db.set_value("Voice Speaker", new_speaker, "sample_audio", file_doc.file_url)
                        with suppress(FileNotFoundError):
                            os.remove(sample_path)

        db = SpeakerDB()

        missing_items = []
        missing_indexes = []
        for i, seg in enumerate(original_results):
            if _has_embedding(_seg_get(seg, "embedding", 4, None)):
                continue
            start = float(_seg_get(seg, "start", 0, 0) or 0)
            end = float(_seg_get(seg, "end", 1, start) or start)
            if end - start < 0.8:
                continue
            missing_indexes.append(i)
            missing_items.append({"wav_path": _ensure_wav(), "start": start, "end": end})
        if missing_items:
            emb_results = _extract_embeddings_from_files_remote(missing_items, task="Bổ sung embedding khi quét lại nhiều speaker")
            for idx, emb in zip(missing_indexes, emb_results):
                if emb is not None:
                    _seg_set_embedding(original_results[idx], emb)

        restored_raw_count = _restore_result_speakers_from_original(results, original_results)
        reassigned_count = 0
        matched_by_speaker = {}
        matched_indexes = set()
        speaker_aliases = _get_speaker_alias_map()
        for i, seg in enumerate(original_results):
            emb = _seg_get(seg, "embedding", 4, None)
            if not _has_embedding(emb):
                continue
            top_match, _ranked = _top_db_match(
                db,
                _normalize_embedding(emb),
                aliases=speaker_aliases,
            )
            if not top_match:
                continue
            matched_name, similarity, email, user_info = top_match
            if i < len(results):
                _seg_set_speaker(results[i], matched_name)
                matched_indexes.add(i)
            matched_by_speaker[matched_name] = matched_by_speaker.get(matched_name, 0) + 1
            reassigned_count += 1

        source_assigned = _assign_by_source_winners(results, original_results, matched_indexes)
        manual_assigned = _apply_manual_speaker_assignments(results, original_results, manual_assignments)
        inherited_by_source = {}
        dropped_unidentifiable = []
        merged_adjacent_count = 0
        final_text = _build_plain_transcript(results)
        frappe.db.set_value("Voice Meeting", meeting_name, {
            "raw_results": json.dumps(results, ensure_ascii=False),
            "original_raw_results": json.dumps(original_results, ensure_ascii=False),
            "transcript": final_text,
        })
        frappe.db.commit()
    finally:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)
        
        return {
            "status": "success",
            "enrolled": enrolled,
            "skipped": skipped,
            "errors": errors,
            "results": results,
            "segment_embedding_rebuild": segment_embedding_rebuild,
            "restored_raw_count": restored_raw_count,
            "reassigned_count": reassigned_count,
            "source_assigned_count": source_assigned["count"],
            "source_assigned_by_speaker": source_assigned["by_speaker"],
            "manual_assigned_count": manual_assigned["count"],
        "manual_assigned_by_speaker": manual_assigned["by_speaker"],
        "matched_by_speaker": matched_by_speaker,
        "inherited_by_source": inherited_by_source,
        "dropped_unidentifiable_count": len(dropped_unidentifiable),
        "dropped_unidentifiable_preview": dropped_unidentifiable[:20],
        "merged_adjacent_count": merged_adjacent_count,
        "message": f"Đã đăng ký/cập nhật {len(enrolled)} giọng, quét lại {reassigned_count} đoạn, gán theo nhóm {source_assigned['count']} đoạn, gán tay {manual_assigned['count']} đoạn"
    }


@frappe.whitelist(allow_guest=False)
def reassign_speaker_from_segment():
    """
    Học giọng từ một đoạn hội thoại cụ thể, sau đó quét lại toàn bộ
    transcript với toàn bộ Voice Speaker DB. Segment nào match DB thì gán
    đúng người đó, không gom/merge các nhãn Speaker còn lại.

    Payload (JSON body):
        meeting_name    : tên Voice Meeting
        segment_index   : index của đoạn hội thoại dùng làm mẫu
        new_speaker_name: tên người nói mới
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    segment_index = int(payload.get("segment_index", -1))
    speaker_aliases = _get_speaker_alias_map()
    new_speaker_name = _normalize_requested_speaker_name(payload.get("new_speaker_name"), speaker_aliases)

    if not meeting_name or segment_index < 0 or not new_speaker_name:
        return {"status": "error", "message": "Thiếu meeting_name, segment_index hoặc new_speaker_name"}

    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not meeting or not meeting.raw_results:
        return {"status": "error", "message": "Không tìm thấy meeting hoặc dữ liệu raw_results"}

    if not _can_access_meeting(meeting.owner):
        return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}
    if not str(meeting.audio_file or "").strip():
        return _missing_audio_rescan_error(meeting)

    results = json.loads(meeting.raw_results)

    if segment_index >= len(results):
        return {"status": "error", "message": f"segment_index {segment_index} vượt quá số đoạn hội thoại ({len(results)})"}

    converted_wav = ""
    try:
        import numpy as np
        from .speaker_manager import SpeakerDB
        from voice_app.audio_utils import convert_to_wav, extract_segment_ffmpeg
        from voice_app.speaker_manager import _extract_embeddings_from_files_remote

        def _seg_get(seg, key, idx=None, default=None):
            if isinstance(seg, dict):
                return seg.get(key, default)
            if idx is not None and len(seg) > idx:
                return seg[idx]
            return default

        def _seg_set_speaker(seg, value):
            if isinstance(seg, dict):
                seg["speaker"] = value
            elif len(seg) > 2:
                seg[2] = value

        def _seg_set_embedding(seg, value):
            emb_list = value.tolist() if hasattr(value, "tolist") else value
            if isinstance(seg, dict):
                seg["embedding"] = emb_list
            elif len(seg) > 4:
                seg[4] = emb_list
            else:
                while len(seg) < 4:
                    seg.append("")
                seg.append(emb_list)

        def _audio_file_path(file_url):
            clean_url = (file_url or "").lstrip("/")
            if not clean_url:
                return ""
            if clean_url.startswith("files/"):
                return frappe.get_site_path("public", clean_url)
            return frappe.get_site_path(clean_url)

        def _normalize_embedding(emb):
            if emb is None:
                return None
            emb_np = np.array(emb, dtype=np.float32)
            norm = np.linalg.norm(emb_np)
            if norm > 0:
                emb_np = emb_np / norm
            return emb_np

        def _has_embedding(emb):
            if emb is None:
                return False
            if isinstance(emb, (list, tuple)) and not emb:
                return False
            return True

        known_speaker_names = None

        def _is_unassigned_speaker(label):
            text = str(label or "").strip()
            if not text:
                return True
            unknown_markers = ("Speaker", "Người lạ", "Unknown", "Không tên")
            if any(marker in text for marker in unknown_markers):
                return True
            if known_speaker_names is not None and text not in known_speaker_names:
                return True
            return False

        def _current_result_speaker(idx):
            if idx < len(results):
                return _seg_get(results[idx], "speaker", 2, "")
            if idx < len(original_results):
                return _seg_get(original_results[idx], "speaker", 2, "")
            return ""

        def _save_sample_audio(speaker_name, wav_path, start, end):
            if not wav_path or not os.path.exists(wav_path):
                return ""
            if not frappe.db.has_column("Voice Speaker", "sample_audio"):
                return ""
            sample_path = extract_segment_ffmpeg(wav_path, start, end, padding=0.1)
            if not sample_path:
                return ""
            try:
                safe_name = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in speaker_name).strip()
                filename = f"{safe_name or 'speaker'}_{int(time.time())}.wav"
                with open(sample_path, "rb") as f:
                    file_doc = save_file(filename, f.read(), "Voice Speaker", speaker_name, is_private=1)
                frappe.db.set_value("Voice Speaker", speaker_name, "sample_audio", file_doc.file_url)
                return file_doc.file_url
            finally:
                with suppress(FileNotFoundError):
                    os.remove(sample_path)

        original_results = json.loads(meeting.original_raw_results) if meeting.original_raw_results else []
        if not original_results:
            original_results = [
                {
                    "start": _seg_get(seg, "start", 0, 0),
                    "end": _seg_get(seg, "end", 1, 0),
                    "speaker": _seg_get(seg, "speaker", 2, ""),
                    "text": _seg_get(seg, "text", 3, ""),
                    "embedding": _seg_get(seg, "embedding", 4, None),
                }
                for seg in results
            ]

        if segment_index >= len(original_results):
            return {"status": "error", "message": f"segment_index {segment_index} vượt quá dữ liệu gốc ({len(original_results)})"}

        segment_embedding_rebuild = _rebuild_segment_embeddings_from_audio(
            meeting,
            original_results,
            force=True,
            min_duration=0.8,
            task="Rebuild từng segment khi quét lại speaker",
        )
        if segment_embedding_rebuild.get("error"):
            return {"status": "error", "message": segment_embedding_rebuild["error"]}

        manual_assignments = _build_manual_assignment_from_segment(results, original_results, segment_index, new_speaker_name)
        target_seg = original_results[segment_index]
        sample_embedding = _seg_get(target_seg, "embedding", 4, None)
        sample_start = float(_seg_get(target_seg, "start", 0, 0) or 0)
        sample_end = float(_seg_get(target_seg, "end", 1, sample_start) or sample_start)

        # Nếu transcript cũ chưa có embedding, tự cắt audio gốc để trích xuất lại.
        # Đây là luồng "chọn tên -> Quét lại AI": enroll đoạn mẫu vào DB rồi
        # quét lại toàn bộ transcript bằng embedding mới.
        wav_path = ""
        if not _has_embedding(sample_embedding):
            audio_path = _audio_file_path(meeting.audio_file)
            if not audio_path or not os.path.exists(audio_path):
                return {"status": "error", "message": "Không tìm thấy file âm thanh gốc để trích xuất giọng nói."}
            converted_wav, err = convert_to_wav(audio_path)
            if err:
                return {"status": "error", "message": f"Lỗi xử lý file âm thanh: {err}"}
            wav_path = converted_wav
            if sample_end - sample_start < 0.8:
                return {"status": "error", "message": "Đoạn âm thanh quá ngắn để học giọng. Hãy chọn đoạn dài hơn."}
            emb_res = _extract_embeddings_from_files_remote(
                [{"wav_path": wav_path, "start": sample_start, "end": sample_end}],
                task="Quét lại speaker từ segment",
            )
            sample_embedding = emb_res[0] if emb_res else None
            if sample_embedding is not None:
                _seg_set_embedding(target_seg, sample_embedding)

        if not _has_embedding(sample_embedding):
            return {"status": "error", "message": "Không thể trích xuất đặc trưng giọng nói từ đoạn đã chọn."}

        if not wav_path and meeting.audio_file:
            audio_path = _audio_file_path(meeting.audio_file)
            if audio_path and os.path.exists(audio_path):
                converted_wav, err = convert_to_wav(audio_path)
                if not err:
                    wav_path = converted_wav

        clean_sample = _clean_speaker_sample_embedding(
            wav_path,
            sample_start,
            sample_end,
            fallback_embedding=sample_embedding,
            task="Lọc sample khi quét lại speaker từ segment",
        )
        sample_emb_np = clean_sample.get("embedding")
        if sample_emb_np is None:
            sample_emb_np = _normalize_embedding(sample_embedding)

        # Bước 2: Với luồng quét lại từ 1 segment, nếu tên đã có trong DB thì
        # không overwrite embedding/sample_audio cũ nữa. Ta chỉ dùng Voice DB
        # hiện có để quét lại toàn meeting, tránh lỡ một segment bẩn làm hỏng
        # luôn mẫu giọng đã enroll trước đó.
        db = SpeakerDB()
        existing_entry = db.speakers.get(new_speaker_name)
        speaker_db_updated = not bool(existing_entry)
        sample_audio_url = ""

        if speaker_db_updated:
            db.add_speaker(new_speaker_name, sample_emb_np, email="", user_info=None)
            sample_audio_url = _save_sample_audio(
                new_speaker_name,
                wav_path,
                clean_sample.get("start") or sample_start,
                clean_sample.get("end") or sample_end,
            )

        known_speaker_names = set(SpeakerDB().speakers.keys())

        # Bổ sung embedding cho các segment còn thiếu để quét lại được rộng hơn.
        if meeting.audio_file:
            if not wav_path:
                audio_path = _audio_file_path(meeting.audio_file)
                if audio_path and os.path.exists(audio_path):
                    converted_wav, err = convert_to_wav(audio_path)
                    if not err:
                        wav_path = converted_wav
            if wav_path:
                missing_items = []
                missing_indexes = []
                for i, seg in enumerate(original_results):
                    if _has_embedding(_seg_get(seg, "embedding", 4, None)):
                        continue
                    start = float(_seg_get(seg, "start", 0, 0) or 0)
                    end = float(_seg_get(seg, "end", 1, start) or start)
                    if end - start < 0.8:
                        continue
                    missing_indexes.append(i)
                    missing_items.append({"wav_path": wav_path, "start": start, "end": end})
                if missing_items:
                    emb_results = _extract_embeddings_from_files_remote(
                        missing_items,
                        task="Bổ sung embedding khi quét lại speaker",
                    )
                    for idx, emb in zip(missing_indexes, emb_results):
                        if emb is not None:
                            _seg_set_embedding(original_results[idx], emb)

        # Bước 3: Reload DB sau khi enroll, rồi scan từng segment với toàn bộ DB.
        # Không so riêng với sample nữa, vì Quét lại AI phải nhận diện mọi
        # người đã có trong Voice Speaker DB và giữ nguyên nhãn raw nếu không match.
        db = SpeakerDB()
        known_speaker_names = set(db.speakers.keys())
        restored_raw_count = _restore_result_speakers_from_original(results, original_results)
        reassigned_count = 0
        matched_by_speaker = {}
        matched_indexes = set()

        speaker_aliases = _get_speaker_alias_map()
        for i, seg in enumerate(original_results):
            seg_emb = _seg_get(seg, "embedding", 4, None)
            if not _has_embedding(seg_emb):
                continue

            seg_emb_np = _normalize_embedding(seg_emb)
            if seg_emb_np is None:
                continue

            top_match, _ranked = _top_db_match(
                db,
                seg_emb_np,
                aliases=speaker_aliases,
            )
            if not top_match:
                continue

            matched_name, similarity, email, user_info = top_match
            if i < len(results):
                _seg_set_speaker(results[i], matched_name)
                matched_indexes.add(i)
            matched_by_speaker[matched_name] = matched_by_speaker.get(matched_name, 0) + 1
            reassigned_count += 1

        source_assigned = _assign_by_source_winners(results, original_results, matched_indexes)
        manual_assigned = _apply_manual_speaker_assignments(results, original_results, manual_assignments)
        inherited_by_source = {}

        # Bước 5: Lưu lại kết quả mới. Segment không match DB vẫn giữ nhãn
        # raw Gemini theo speaker trong chunk, để user còn thấy đúng nhóm lạ.
        dropped_unidentifiable = []
        merged_adjacent_count = 0
        final_text = _build_plain_transcript(results)
        frappe.db.set_value("Voice Meeting", meeting_name, {
            "raw_results": json.dumps(results, ensure_ascii=False),
            "original_raw_results": json.dumps(original_results, ensure_ascii=False),
            "transcript": final_text,
        })
        frappe.db.commit()

        return {
            "status": "success",
            "results": results,
            "restored_raw_count": restored_raw_count,
            "reassigned_count": reassigned_count,
            "source_assigned_count": source_assigned["count"],
            "source_assigned_by_speaker": source_assigned["by_speaker"],
            "manual_assigned_count": manual_assigned["count"],
            "manual_assigned_by_speaker": manual_assigned["by_speaker"],
            "segment_embedding_rebuild": segment_embedding_rebuild,
            "matched_by_speaker": matched_by_speaker,
            "inherited_by_source": inherited_by_source,
            "dropped_unidentifiable_count": len(dropped_unidentifiable),
            "dropped_unidentifiable_preview": dropped_unidentifiable[:20],
            "merged_adjacent_count": merged_adjacent_count,
            "speaker_db_updated": speaker_db_updated,
            "sample_audio": sample_audio_url,
            "message": (
                f"Đã quét lại DB giọng nói, gán {reassigned_count} đoạn, "
                f"gán theo nhóm {source_assigned['count']} đoạn, "
                f"gán tay {manual_assigned['count']} đoạn"
                + (
                    f", đã thêm mẫu giọng mới cho {new_speaker_name}"
                    if speaker_db_updated else
                    f", giữ nguyên mẫu giọng hiện có của {new_speaker_name}"
                )
            )
        }

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Reassign Speaker From Segment Error")
        return {"status": "error", "message": str(e)}
    finally:
        try:
            if converted_wav and os.path.exists(converted_wav):
                os.remove(converted_wav)
        except Exception:
            pass


@frappe.whitelist(allow_guest=False)
def rescan_meeting_from_current_labels(**kwargs):
    """
    Dùng nhãn speaker hiện tại trong transcript (sau khi user sửa ở phần dưới)
    làm manual/source assignments, enroll những tên chưa có trong DB, rồi quét
    lại toàn bộ meeting đúng một lần.
    """
    meeting_name = kwargs.get("meeting_name")
    if not meeting_name:
        try:
            data = frappe.request.get_data()
            payload = json.loads(data)
            meeting_name = payload.get("meeting_name")
        except Exception:
            pass

    if not meeting_name:
        return {"status": "error", "message": "Thiếu meeting_name"}

    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not meeting or not meeting.raw_results:
        return {"status": "error", "message": "Không tìm thấy meeting hoặc dữ liệu raw_results"}
    if not _can_access_meeting(meeting.owner):
        return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}
    if not str(meeting.audio_file or "").strip():
        return _missing_audio_rescan_error(meeting)

    results = json.loads(meeting.raw_results)
    original_results = json.loads(meeting.original_raw_results) if meeting.original_raw_results else []

    def _seg_set_embedding(seg, value):
        emb_list = value.tolist() if hasattr(value, "tolist") else value
        if isinstance(seg, dict):
            seg["embedding"] = emb_list
        elif len(seg) > 4:
            seg[4] = emb_list
        else:
            while len(seg) < 4:
                seg.append("")
            seg.append(emb_list)

    def _has_embedding(emb):
        if emb is None:
            return False
        if isinstance(emb, (list, tuple)) and not emb:
            return False
        return True

    def _normalize_embedding(emb):
        return _normalize_np_embedding(emb)

    def _audio_file_path(file_url):
        clean_url = (file_url or "").lstrip("/")
        if not clean_url:
            return ""
        if clean_url.startswith("files/"):
            return frappe.get_site_path("public", clean_url)
        return frappe.get_site_path(clean_url)

    def _save_sample_audio(speaker_name, wav_path, start, end):
        if not wav_path or not os.path.exists(wav_path):
            return ""
        if not frappe.db.has_column("Voice Speaker", "sample_audio"):
            return ""
        from voice_app.audio_utils import extract_segment_ffmpeg
        sample_path = extract_segment_ffmpeg(wav_path, start, end, padding=0.1)
        if not sample_path:
            return ""
        try:
            safe_name = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in speaker_name).strip()
            filename = f"{safe_name or 'speaker'}_{int(time.time())}.wav"
            with open(sample_path, "rb") as f:
                file_doc = save_file(filename, f.read(), "Voice Speaker", speaker_name, is_private=1)
            frappe.db.set_value("Voice Speaker", speaker_name, "sample_audio", file_doc.file_url)
            return file_doc.file_url
        finally:
            with suppress(FileNotFoundError):
                os.remove(sample_path)

    if not original_results:
        original_results = [
            {
                "start": _seg_get(seg, "start", 0, 0),
                "end": _seg_get(seg, "end", 1, 0),
                "speaker": _seg_get(seg, "speaker", 2, ""),
                "text": _seg_get(seg, "text", 3, ""),
                "embedding": _seg_get(seg, "embedding", 4, None),
            }
            for seg in results
        ]

    speaker_aliases = _get_speaker_alias_map()
    manual_assignments, candidate_sample_indexes = _build_manual_assignments_from_current_results(
        results,
        original_results,
        aliases=speaker_aliases,
    )
    if not manual_assignments:
        return {"status": "error", "message": "Chưa có tên đã sửa ở transcript để quét lại AI."}

    enrolled = []
    skipped = []
    errors = []
    db = SpeakerDB()
    sample_indexes = {}

    for speaker_name, idx in candidate_sample_indexes.items():
        current = frappe.get_all("Voice Speaker", filters={"speaker_name": speaker_name}, fields=["name", "embedding"])
        if current and current[0].get("embedding"):
            skipped.append(speaker_name)
        else:
            sample_indexes[speaker_name] = idx

    wav_path = ""
    segment_embedding_rebuild = {"rebuilt": 0, "skipped_short": 0}
    restored_raw_count = 0
    reassigned_count = 0
    matched_by_speaker = {}
    source_assigned = {"count": 0, "by_speaker": {}}
    manual_assigned = {"count": 0, "by_speaker": {}}
    dropped_unidentifiable = []
    new_sample_audio = {}

    try:
        from voice_app.speaker_manager import _extract_embeddings_from_files_remote
        from voice_app.audio_utils import concat_speaker_segments, get_duration

        def _save_sample_audio_from_file(speaker_name, src_path):
            if not src_path or not os.path.exists(src_path):
                return ""
            if not frappe.db.has_column("Voice Speaker", "sample_audio"):
                return ""
            safe_name = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in speaker_name).strip()
            filename = f"{safe_name or 'speaker'}_{int(time.time())}.wav"
            with open(src_path, "rb") as f:
                file_doc = save_file(filename, f.read(), "Voice Speaker", speaker_name, is_private=1)
            frappe.db.set_value("Voice Speaker", speaker_name, "sample_audio", file_doc.file_url)
            return file_doc.file_url

        def _ensure_wav():
            nonlocal wav_path
            if wav_path:
                return wav_path
            audio_path = _audio_file_path(meeting.audio_file)
            if not audio_path or not os.path.exists(audio_path):
                raise RuntimeError("Không tìm thấy file âm thanh gốc để trích xuất giọng nói.")
            wav_path, err = convert_to_wav(audio_path)
            if err:
                raise RuntimeError(f"Lỗi xử lý file âm thanh: {err}")
            return wav_path

        segment_embedding_rebuild = _rebuild_segment_embeddings_from_audio(
            meeting,
            original_results,
            force=True,
            min_duration=0.8,
            task="Rebuild từng segment khi quét lại từ transcript",
        )
        if segment_embedding_rebuild.get("error"):
            return {"status": "error", "message": segment_embedding_rebuild["error"]}

        missing_samples = []
        missing_sample_names = []
        for speaker_name, idx in sample_indexes.items():
            seg = original_results[idx] if idx < len(original_results) else results[idx]
            emb = _seg_get(seg, "embedding", 4, None)
            if _has_embedding(emb):
                continue
            start = float(_seg_get(seg, "start", 0, 0) or 0)
            end = float(_seg_get(seg, "end", 1, start) or start)
            missing_sample_names.append(speaker_name)
            missing_samples.append({"wav_path": _ensure_wav(), "start": start, "end": end})
        if missing_samples:
            emb_results = _extract_embeddings_from_files_remote(
                missing_samples,
                task="Đăng ký giọng từ transcript đã sửa",
            )
            for speaker_name, emb in zip(missing_sample_names, emb_results):
                idx = sample_indexes[speaker_name]
                if emb is not None and idx < len(original_results):
                    _seg_set_embedding(original_results[idx], emb)

        # Cắt sẵn mẫu giọng cho mọi speaker_id bằng cách gom cụm — chạy đúng
        # một lần vì mỗi lần gom cụm tốn vài trăm lượt trích embedding. Mẫu lấy
        # từ cụm chứ không cắt theo start/end của segment: mốc thời gian có thể
        # lệch hàng trăm giây nên cắt theo đó dễ ra giọng người bên cạnh.
        cluster_samples, cluster_of_sid = {}, {}
        if candidate_sample_indexes:
            try:
                from voice_app.speaker_manager import build_voice_samples_by_clustering

                cluster_samples, cluster_of_sid = build_voice_samples_by_clustering(
                    _ensure_wav(),
                    original_results,
                    task="Đăng ký giọng theo cụm khi quét lại",
                )
            except Exception as exc:
                cluster_samples, cluster_of_sid = {}, {}
                print(f"[Rescan] gom cụm giọng lỗi, dùng cách cũ: {exc!r}")

        # speaker_id đại diện cho từng tên user vừa gõ — tính cho MỌI tên, kể
        # cả tên đã có giọng trong DB, vì bước gán nhãn phía dưới cần đủ.
        dominant_sid_by_name = {}

        used_samples = set()
        for speaker_name, idx in candidate_sample_indexes.items():
            # Tên do user gán nằm ở bản hiển thị; muốn biết lấy mẫu giọng nào
            # thì phải lần về speaker_id thô của Gemini. Lấy speaker_id chiếm
            # nhiều lời nhất trong số đoạn user đã gán tên này.
            from collections import Counter

            sid_weight = Counter()
            matching_segs = []
            for i, display_seg in enumerate(results or []):
                label = _normalize_requested_speaker_name(
                    _seg_get(display_seg, "speaker", 2, ""),
                    speaker_aliases,
                )
                if label != speaker_name:
                    continue
                orig_seg = original_results[i] if i < len(original_results) else display_seg
                sid = orig_seg.get("speaker_id") if isinstance(orig_seg, dict) else None
                if sid:
                    sid_weight[sid] += len(str(_seg_get(orig_seg, "text", 3, "") or "").split())
                seg_start = float(_seg_get(orig_seg, "start", 0, 0) or 0)
                seg_end = float(_seg_get(orig_seg, "end", 1, seg_start) or seg_start)
                if seg_end > seg_start:
                    matching_segs.append({"start": seg_start, "end": seg_end})

            clean_emb = None
            group_start = group_end = None
            concat_wav_path = None

            dominant_sid = sid_weight.most_common(1)[0][0] if sid_weight else None
            if dominant_sid:
                dominant_sid_by_name[speaker_name] = dominant_sid

            # Tên đã có giọng trong DB thì không học lại, nhưng vẫn phải ghi
            # nhận speaker_id ở trên để bước gán nhãn biết đường lan tên.
            if speaker_name not in sample_indexes:
                continue

            if dominant_sid and dominant_sid in cluster_samples:
                concat_wav_path = cluster_samples[dominant_sid]
                used_samples.add(dominant_sid)
            elif len(matching_segs) > 1:
                concat_wav_path = concat_speaker_segments(_ensure_wav(), matching_segs, max_total_sec=25.0, min_seg_sec=1.5)
                if concat_wav_path is None:
                    concat_wav_path = concat_speaker_segments(_ensure_wav(), matching_segs, max_total_sec=25.0, min_seg_sec=0.0)

            if concat_wav_path:
                dur = get_duration(concat_wav_path)
                emb_results_c = _extract_embeddings_from_files_remote(
                    [{"wav_path": concat_wav_path, "start": 0.0, "end": dur}],
                    task="Enroll speaker khi quét lại (cụm giọng)",
                )
                if emb_results_c and emb_results_c[0] is not None:
                    clean_emb = _normalize_embedding(emb_results_c[0])

            if clean_emb is None:
                # Chỉ 1 đoạn (hoặc ghép nhiều đoạn thất bại) — về lại cách cũ:
                # lọc trong nội bộ đoạn đại diện dài nhất.
                seg = original_results[idx] if idx < len(original_results) else results[idx]
                emb = _seg_get(seg, "embedding", 4, None)
                if not _has_embedding(emb):
                    errors.append(f"{speaker_name} (Không trích được embedding)")
                    continue
                start = float(_seg_get(seg, "start", 0, 0) or 0)
                end = float(_seg_get(seg, "end", 1, start) or start)
                if end - start < 2.0:
                    errors.append(f"{speaker_name} (Audio quá ngắn, cần > 2s)")
                    continue

                clean_sample = _clean_speaker_sample_embedding(
                    _ensure_wav(),
                    start,
                    end,
                    fallback_embedding=emb,
                    task="Lọc sample khi quét lại từ transcript",
                )
                clean_emb_tmp = clean_sample.get("embedding")
                clean_emb = clean_emb_tmp if clean_emb_tmp is not None else _normalize_embedding(emb)
                group_start = clean_sample.get("start") or start
                group_end = clean_sample.get("end") or end

            db.add_speaker(speaker_name, clean_emb, email="", user_info=None)
            enrolled.append(speaker_name)
            if concat_wav_path and os.path.exists(concat_wav_path):
                new_sample_audio[speaker_name] = _save_sample_audio_from_file(speaker_name, concat_wav_path)
                with suppress(FileNotFoundError):
                    os.remove(concat_wav_path)
            else:
                new_sample_audio[speaker_name] = _save_sample_audio(
                    speaker_name,
                    _ensure_wav(),
                    group_start,
                    group_end,
                )

        # Mẫu của speaker_id không ai nhận tên thì bỏ, khỏi để lại file rác.
        for sid, path in cluster_samples.items():
            if sid not in used_samples and path and os.path.exists(path):
                with suppress(FileNotFoundError):
                    os.remove(path)

        db = SpeakerDB()

        missing_items = []
        missing_indexes = []
        for i, seg in enumerate(original_results):
            if _has_embedding(_seg_get(seg, "embedding", 4, None)):
                continue
            start = float(_seg_get(seg, "start", 0, 0) or 0)
            end = float(_seg_get(seg, "end", 1, start) or start)
            if end - start < 0.8:
                continue
            missing_indexes.append(i)
            missing_items.append({"wav_path": _ensure_wav(), "start": start, "end": end})
        if missing_items:
            emb_results = _extract_embeddings_from_files_remote(
                missing_items,
                task="Bổ sung embedding khi quét lại từ transcript",
            )
            for idx, emb in zip(missing_indexes, emb_results):
                if emb is not None:
                    _seg_set_embedding(original_results[idx], emb)

        restored_raw_count = _restore_result_speakers_from_original(results, original_results)
        matched_indexes = set()

        # Gán tên theo đúng nhãn người dùng vừa gõ, lan sang các speaker_id
        # cùng một giọng.
        #
        # Trước đây bước này còn dò lại cả file: lấy embedding từng đoạn rồi so
        # với DB xem giống ai nhất. Nhưng người dùng đã tự tai nghe và gõ tên
        # rồi — để máy đoán lại là mở đường cho nó ghi đè bằng phán đoán sai,
        # trong khi tên gõ tay mới là thứ đáng tin nhất ở đây. Nay chỉ dùng
        # gom cụm để biết speaker_id nào thật ra cùng một người (Gemini hay
        # tách một giọng thành nhiều id), rồi chép tên đó sang.
        name_by_sid = {}
        for speaker_name, dom_sid in dominant_sid_by_name.items():
            name_by_sid[dom_sid] = speaker_name
            cluster_id = cluster_of_sid.get(dom_sid)
            if cluster_id is None:
                continue
            for sid, cid in cluster_of_sid.items():
                if cid == cluster_id:
                    name_by_sid[sid] = speaker_name

        # Giọng nào không lần ra được người thì trả về Speaker N, không giữ
        # lại tên cũ. Tên cũ vốn do lần nhận diện trước đoán ra, mà đã đoán
        # thì có thể sai — để nguyên là người đọc biên bản tưởng đã xác minh.
        # Cũng không dựa vào mốc thời gian để đoán bù, vì mốc chỉ là ước lượng
        # rải chữ lên vùng có tiếng chứ không đo từng chữ.
        def _gemini_speaker_label(speaker_id, fallback_index):
            """Lấy lại đúng nhãn Gemini đã đặt, ví dụ c0_speaker_2 -> Speaker 2.

            Không tự đánh số lại: người dùng đối chiếu biên bản với thứ tự
            Gemini chia, đánh lại từ đầu là hai bên lệch nhau.
            """
            match = re.search(r"speaker[_\s-]*(\d+)", str(speaker_id or ""), re.IGNORECASE)
            if match:
                return f"Speaker {int(match.group(1))}"
            return f"Speaker {fallback_index}"

        unknown_ids = {}
        for i, seg in enumerate(original_results):
            if i >= len(results):
                continue
            sid = seg.get("speaker_id") if isinstance(seg, dict) else None
            matched_name = name_by_sid.get(sid)
            if matched_name:
                _seg_set_speaker_value(results[i], matched_name)
                matched_indexes.add(i)
                matched_by_speaker[matched_name] = matched_by_speaker.get(matched_name, 0) + 1
                reassigned_count += 1
                continue
            if sid not in unknown_ids:
                unknown_ids[sid] = _gemini_speaker_label(sid, len(unknown_ids) + 1)
            _seg_set_speaker_value(results[i], unknown_ids[sid])
        if unknown_ids:
            print(f"[Rescan] chưa lần ra người cho: {unknown_ids}")

        source_assigned = _assign_by_source_winners(results, original_results, matched_indexes)
        manual_assigned = _apply_manual_speaker_assignments(results, original_results, manual_assignments)

        # Gộp luôn các đoạn liền kề của cùng một người. Trước đây phải bấm
        # thêm nút "Chuẩn hoá hội thoại" mới làm việc này, nhưng nó chỉ có
        # nghĩa sau khi tên đã chốt — tức là ngay đây. Để riêng một nút chỉ
        # khiến người dùng phải nhớ bấm đúng thứ tự.
        results, original_results, merged_adjacent_count = _merge_adjacent_same_speaker_segments(
            results,
            original_results,
        )
        final_text = _build_plain_transcript(results)
        frappe.db.set_value("Voice Meeting", meeting_name, {
            "raw_results": json.dumps(results, ensure_ascii=False),
            "original_raw_results": json.dumps(original_results, ensure_ascii=False),
            "transcript": final_text,
        })
        frappe.db.commit()

        return {
            "status": "success",
            "results": results,
            "enrolled": enrolled,
            "skipped": skipped,
            "errors": errors,
            "restored_raw_count": restored_raw_count,
            "reassigned_count": reassigned_count,
            "source_assigned_count": source_assigned["count"],
            "source_assigned_by_speaker": source_assigned["by_speaker"],
            "manual_assigned_count": manual_assigned["count"],
            "manual_assigned_by_speaker": manual_assigned["by_speaker"],
            "segment_embedding_rebuild": segment_embedding_rebuild,
            "matched_by_speaker": matched_by_speaker,
            "dropped_unidentifiable_count": len(dropped_unidentifiable),
            "dropped_unidentifiable_preview": dropped_unidentifiable[:20],
            "merged_adjacent_count": merged_adjacent_count,
            "new_sample_audio": new_sample_audio,
            "message": (
                f"Đã quét lại theo tên đã sửa, gán {reassigned_count} đoạn, "
                f"gán theo nhóm {source_assigned['count']} đoạn, "
                f"gán tay {manual_assigned['count']} đoạn"
                + (f", đăng ký giọng mới: {', '.join(enrolled)}" if enrolled else "")
                + (f", giữ nguyên giọng có sẵn: {', '.join(skipped)}" if skipped else "")
            ),
        }
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Rescan Meeting From Current Labels Error")
        return {"status": "error", "message": str(e)}
    finally:
        if wav_path and os.path.exists(wav_path):
            with suppress(FileNotFoundError):
                os.remove(wav_path)


@frappe.whitelist(allow_guest=False)
def normalize_meeting_transcript():
    """
    Chuẩn hoá transcript sau khi user đã chốt speaker/text:
    chỉ gộp các đoạn liền kề đã cùng speaker final và nối câu nhẹ nhàng.
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")

    if not meeting_name:
        return {"status": "error", "message": "Thiếu meeting_name"}

    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not meeting or not meeting.raw_results:
        return {"status": "error", "message": "Không tìm thấy meeting hoặc dữ liệu raw_results"}
    if not _can_access_meeting(meeting.owner):
        return {"status": "error", "message": "Không có quyền chỉnh sửa meeting này"}

    results = json.loads(meeting.raw_results)
    original_results = json.loads(meeting.original_raw_results) if meeting.original_raw_results else []
    if not original_results:
        original_results = [
            {
                "start": _seg_get(seg, "start", 0, 0),
                "end": _seg_get(seg, "end", 1, 0),
                "speaker": _seg_get(seg, "speaker", 2, ""),
                "text": _seg_get(seg, "text", 3, ""),
                "embedding": _seg_get(seg, "embedding", 4, None),
            }
            for seg in results
        ]

    # Không bắt phải gán hết tên mới cho gộp. Việc gộp chỉ nối các đoạn liền
    # kề đã cùng một nhãn, nên Speaker 1 gộp với Speaker 1 vẫn đúng — chưa
    # biết tên thật thì cũng không sao. Bắt gán hết trước chỉ khiến người dùng
    # phải làm xong việc khó mới được làm việc dễ.
    unknown_labels = sorted({
        str(_seg_get(seg, "speaker", 2, "") or "").strip() or "Không tên"
        for seg in results
        if _is_unknown_label_text(str(_seg_get(seg, "speaker", 2, "") or "").strip())
    })

    merged_results, merged_original_results, merged_adjacent_count = _merge_adjacent_same_speaker_segments(
        results,
        original_results,
    )
    final_text = _build_plain_transcript(merged_results)
    frappe.db.set_value("Voice Meeting", meeting_name, {
        "raw_results": json.dumps(merged_results, ensure_ascii=False),
        "original_raw_results": json.dumps(merged_original_results, ensure_ascii=False),
        "transcript": final_text,
    })
    frappe.db.commit()

    message = (
        f"Đã chuẩn hoá hội thoại, gộp {merged_adjacent_count} đoạn liền kề cùng người nói."
        if merged_adjacent_count
        else "Đã chuẩn hoá hội thoại, không có đoạn nào cần gộp thêm."
    )
    if unknown_labels:
        # Nhắc thôi, không chặn: còn ai chưa có tên thì người dùng tự quyết
        # gán tiếp hay để vậy.
        message += f" Còn {len(unknown_labels)} giọng chưa đặt tên: {', '.join(unknown_labels[:5])}."

    return {
        "status": "success",
        "results": merged_results,
        "merged_adjacent_count": merged_adjacent_count,
        "remaining_unknown_labels": unknown_labels,
        "remaining_unknown_count": len(unknown_labels),
        "message": message,
    }

@frappe.whitelist(allow_guest=False)
def reprocess_meeting_from_raw_chunks(meeting_name=None):
    """
    Chạy lại luồng gộp thoại và đối soát người nói từ raw_segments của các chunk trong DB
    MÀ KHÔNG CẦN TỐN CHI PHÍ / THỜI GIAN GỌI LẠI GEMINI STT API.
    """
    if not meeting_name:
        with suppress(Exception):
            data = frappe.request.get_data()
            if data:
                payload = json.loads(data)
                meeting_name = payload.get("meeting_name")

    if not meeting_name:
        frappe.throw("Thiếu meeting_name")

    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not _can_access_meeting(meeting.owner):
        frappe.throw("Không có quyền chỉnh sửa meeting này", frappe.PermissionError)

    chunk_docs = frappe.get_all("Voice Meeting Chunk", filters={"meeting": meeting_name}, fields=["name", "raw_segments"], order_by="chunk_index asc")
    if not chunk_docs:
        frappe.throw("Không tìm thấy các chunk gốc của cuộc họp này")

    segments = []
    for c in chunk_docs:
        if c.raw_segments:
            with suppress(Exception):
                data = json.loads(c.raw_segments)
                if data.get("segments"):
                    segments.extend(data["segments"])

    if not segments:
        frappe.throw("Không tìm thấy dữ liệu raw_segments trong các chunk")

    segments.sort(key=lambda x: float(x.get("start", 0) or 0))

    # ── SPEAKER DB SCANNING & IDENTIFICATION ─────────────────────────────
    speaker_cache = {}
    import re
    if meeting.stt_parse_log:
        for line in meeting.stt_parse_log.splitlines():
            if '[Speaker] Greedy result' in line or 'Stranger DB rematch' in line:
                matches = re.findall(r'(\w+_\w+)\s*(?:→|->)\s*\'([^\']+)\'', line)
                for raw_id, name in matches:
                    if name and name != 'Speaker':
                        speaker_cache[raw_id] = f'👤 {name}'

    actual_stranger_counter = 1
    real_stranger_map = {}
    for seg in segments:
        raw_id = str(seg.get("speaker_id") or "").strip()
        if raw_id and raw_id not in speaker_cache:
            if raw_id not in real_stranger_map:
                real_stranger_map[raw_id] = f"Speaker {actual_stranger_counter}"
                actual_stranger_counter += 1
            speaker_cache[raw_id] = f"👤 {real_stranger_map[raw_id]}"

    MERGE_GAP = 1.5
    merged_segments = []
    omitted_segment_barrier = False

    for seg in segments:
        import re
        txt = " ".join(str(seg.get("text", "")).split())
        txt = re.sub(r'\.{2,}', ' ', txt)
        txt = " ".join(txt.split()).strip()

        if not txt or not _is_meaningful_transcript_text(txt):
            omitted_segment_barrier = True
            continue

        raw_spk_id = str(seg.get("speaker_id") or "").strip()
        spk_label = speaker_cache.get(raw_spk_id) or str(seg.get("speaker") or seg.get("speaker_id") or "Speaker").strip()
        if not spk_label.startswith("👤 "):
            spk_label = f"👤 {spk_label}"

        emb = seg.get("embedding")
        seg_start = float(seg.get("start", 0) or 0)
        seg_end = float(seg.get("end", 0) or 0)

        if (
            merged_segments
            and not omitted_segment_barrier
            and merged_segments[-1][2] == spk_label
            and len(merged_segments[-1]) > 5
            and merged_segments[-1][5] == raw_spk_id
            and seg_start - float(merged_segments[-1][1] or 0) <= MERGE_GAP
        ):
            prev_s, prev_e, prev_spk, prev_txt, prev_emb, _prev_raw = merged_segments[-1]
            merged_segments[-1] = (prev_s, seg_end, prev_spk, prev_txt + " " + txt, prev_emb if prev_emb is not None else emb, raw_spk_id)
        else:
            merged_segments.append((seg_start, seg_end, spk_label, txt, emb, raw_spk_id))
        omitted_segment_barrier = False

    ui_results = []
    original_results = []
    for row in merged_segments:
        s, e, spk_label, txt, emb = row[:5]
        raw_spk_id = row[5] if len(row) > 5 else ""
        ui_results.append((s, e, spk_label, txt))
        original_results.append({
            "start": s,
            "end": e,
            "speaker": spk_label,
            "text": txt,
            "embedding": emb,
            "speaker_id": raw_spk_id
        })

    final_text = _build_plain_transcript(ui_results)

    frappe.db.set_value("Voice Meeting", meeting_name, {
        "raw_results": json.dumps(ui_results, ensure_ascii=False),
        "original_raw_results": json.dumps(original_results, ensure_ascii=False),
        "transcript": final_text,
    }, update_modified=False)
    frappe.db.commit()

    return {
        "status": "success",
        "meeting_name": meeting_name,
        "results": ui_results,
        "final_text": final_text,
        "message": f"Đã gộp thoại lại thành công cho {meeting_name} (Miễn phí 100%, không gọi lại Gemini STT API)."
    }

@frappe.whitelist(allow_guest=False)
def enroll_speaker_from_segment():
    """
    Lưu đặc trưng giọng nói (embedding) của đoạn hội thoại vào hệ thống (Voice Speaker).
    API này không gán lại tên cho các đoạn khác (không Quét lại AI), chỉ học giọng.
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}

    data = frappe.request.get_data()
    payload = json.loads(data)
    meeting_name = payload.get("meeting_name")
    segment_index = int(payload.get("segment_index", -1))
    new_speaker_name = (payload.get("new_speaker_name") or "").strip()

    if not meeting_name or segment_index < 0 or not new_speaker_name:
        return {"status": "error", "message": "Thiếu thông tin để đăng ký giọng nói."}

    meeting = frappe.get_doc("Voice Meeting", meeting_name)
    if not meeting or not meeting.original_raw_results:
        return {"status": "error", "message": "Không tìm thấy dữ liệu gốc để đăng ký giọng nói."}

    original_results = json.loads(meeting.original_raw_results)
    if segment_index >= len(original_results):
        return {"status": "error", "message": "Đoạn hội thoại không hợp lệ."}

    target_seg = original_results[segment_index]
    sample_embedding = target_seg.get("embedding")

    if not sample_embedding:
        return {"status": "error", "message": "Đoạn hội thoại này chưa được trích xuất dữ liệu giọng nói (embedding)."}

    try:
        import numpy as np
        from .speaker_manager import SpeakerDB, _extract_embeddings_from_files_remote
        from .audio_utils import concat_speaker_segments, get_duration

        sample_start = float(target_seg.get("start") or 0)
        sample_end = float(target_seg.get("end") or sample_start)
        wav_path = ""
        converted_wav = ""
        # Khai báo trước khi vào try: khối finally phía dưới có dọn file theo
        # biến này, mà lỗi có thể xảy ra ngay từ bước chuyển đổi audio — lúc đó
        # finally sẽ vỡ vì biến chưa tồn tại và nuốt mất lỗi thật.
        concat_wav = None
        try:
            clean_url = (meeting.audio_file or "").lstrip("/")
            audio_path = frappe.get_site_path(clean_url) if clean_url else ""
            if audio_path and os.path.exists(audio_path):
                converted_wav, err = convert_to_wav(audio_path)
                if not err:
                    wav_path = converted_wav

            # Học giọng từ CỤM giọng chứa đoạn được click, chứ không cắt audio
            # theo start/end của segment. Mốc thời gian của segment do Gemini
            # đoán hoặc forced-align suy ra và có thể lệch hàng trăm giây, cắt
            # theo đó thì mẫu đăng ký dính giọng người bên cạnh — đúng lỗi làm
            # một người biến mất khỏi biên bản. Gom cụm dựa trên VAD nên biên
            # đoạn luôn nằm trong lời thật của người đó.
            raw_speaker_id = target_seg.get("speaker_id")
            sample_emb_np = None
            group_start = sample_start
            group_end = sample_end

            if wav_path and raw_speaker_id:
                from .speaker_manager import build_voice_samples_by_clustering

                samples, _cluster_of = build_voice_samples_by_clustering(
                    wav_path,
                    original_results,
                    task="Đăng ký giọng theo cụm",
                )
                concat_wav = samples.pop(raw_speaker_id, None)
                for leftover in samples.values():  # mẫu của người khác, không dùng
                    with suppress(FileNotFoundError):
                        os.remove(leftover)
                if concat_wav:
                    dur = get_duration(concat_wav)
                    emb_results = _extract_embeddings_from_files_remote(
                        [{"wav_path": concat_wav, "start": 0.0, "end": dur}],
                        task="Enroll speaker (cụm giọng)",
                    )
                    if emb_results and emb_results[0] is not None:
                        sample_emb_np = _normalize_np_embedding(emb_results[0])

            if sample_emb_np is None:
                # Chỉ 1 đoạn (hoặc ghép nhiều đoạn thất bại) — về lại cách cũ:
                # lọc trong nội bộ đoạn được click.
                clean_sample = _clean_speaker_sample_embedding(
                    wav_path,
                    sample_start,
                    sample_end,
                    fallback_embedding=sample_embedding,
                    task="Lọc sample khi enroll speaker",
                )
                sample_emb_np = clean_sample.get("embedding")
                group_start = clean_sample.get("start") or sample_start
                group_end = clean_sample.get("end") or sample_end
                if sample_emb_np is None:
                    sample_emb_np = np.array(sample_embedding)
                    norm = np.linalg.norm(sample_emb_np)
                    if norm > 0:
                        sample_emb_np = sample_emb_np / norm

            db = SpeakerDB()
            db.add_speaker(new_speaker_name, sample_emb_np, email="", user_info=None)

            sample_audio_url = ""
            if frappe.db.has_column("Voice Speaker", "sample_audio"):
                sample_path = None
                try:
                    if concat_wav and os.path.exists(concat_wav):
                        sample_path = concat_wav
                    elif wav_path:
                        from voice_app.audio_utils import extract_segment_ffmpeg
                        sample_path = extract_segment_ffmpeg(wav_path, group_start, group_end, padding=0.1)

                    if sample_path and os.path.exists(sample_path):
                        safe_name = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in new_speaker_name).strip()
                        with open(sample_path, "rb") as f:
                            file_doc = save_file(f"{safe_name or 'speaker'}_{int(time.time())}.wav", f.read(), "Voice Speaker", new_speaker_name, is_private=1)
                        frappe.db.set_value("Voice Speaker", new_speaker_name, "sample_audio", file_doc.file_url)
                        sample_audio_url = file_doc.file_url
                finally:
                    if sample_path and sample_path != concat_wav:
                        with suppress(FileNotFoundError):
                            os.remove(sample_path)
        finally:
            if converted_wav and os.path.exists(converted_wav):
                os.remove(converted_wav)
            if concat_wav and os.path.exists(concat_wav):
                with suppress(FileNotFoundError):
                    os.remove(concat_wav)

        return {"status": "success", "sample_audio": sample_audio_url, "message": f"Đã học giọng nói của {new_speaker_name} thành công!"}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Enroll Speaker From Segment Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_current_user():
    return frappe.session.user


@frappe.whitelist(allow_guest=False)
def get_enrolled_speakers():
    """Trả về danh sách người đã đăng ký giọng nói trong Voice DB."""
    try:
        speakers = frappe.get_all(
            "Voice Speaker",
            fields=["speaker_name", "email"],
            order_by="speaker_name asc"
        )
        aliases = _build_speaker_alias_map(speakers)
        speakers = [
            speaker
            for speaker in speakers
            if aliases.get((speaker.get("speaker_name") or "").strip(), (speaker.get("speaker_name") or "").strip())
            == (speaker.get("speaker_name") or "").strip()
        ]
        # Enrich với designation từ CTERP nếu có email khớp
        try:
            raw_employees = get_cached_employees()
            erp_map = {e["user_id"]: e for e in raw_employees if e.get("user_id")}
            for spk in speakers:
                if spk.get("email") and spk["email"] in erp_map:
                    spk["designation"] = erp_map[spk["email"]].get("designation", "")
                else:
                    spk["designation"] = ""
        except Exception as exc:
            frappe.log_error(str(exc), "Get Enrolled Speakers Designation Error")
            for spk in speakers:
                spk["designation"] = ""
        return {"status": "success", "speakers": speakers}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Get Enrolled Speakers Error")
        return {"status": "error", "speakers": [], "message": str(e)}

@frappe.whitelist(allow_guest=False)
def get_meeting_history():
    """
    Trả danh sách meeting nhẹ cho sidebar/history modal.
    Nội dung lớn như transcript/raw_results được tải riêng khi mở meeting.
    """
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập", "meetings": []}

    try:
        filters = {}
        if not _can_access_meeting("__admin_history_sentinel__"):
            filters = {"owner": frappe.session.user}
        meetings = frappe.get_all(
            "Voice Meeting",
            filters=filters,
            fields=["name", "title", "date", "status", "audio_file", "minute_docx", "task_xlsx", "modified"],
            order_by="creation desc"
        )
        return {"status": "success", "meetings": meetings}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Get Meeting History Error")
        return {"status": "error", "message": str(e), "meetings": []}


@frappe.whitelist(allow_guest=False)
def get_meeting_detail(meeting_name):
    """Trả chi tiết một meeting khi user bấm mở từ lịch sử."""
    if frappe.session.user == "Guest":
        return {"status": "error", "message": "Vui lòng đăng nhập"}
    if not meeting_name or not frappe.db.exists("Voice Meeting", meeting_name):
        return {"status": "error", "message": "Không tìm thấy meeting"}

    try:
        meeting = frappe.get_doc("Voice Meeting", meeting_name)
        if not _can_access_meeting(meeting.owner):
            return {"status": "error", "message": "Không có quyền xem meeting này"}

        return {
            "status": "success",
            "meeting": {
                "name": meeting.name,
                "title": meeting.title,
                "date": meeting.date,
                "status": meeting.status,
                "audio_file": meeting.audio_file,
                "minute_docx": meeting.minute_docx,
                "task_xlsx": meeting.task_xlsx,
                "transcript": meeting.transcript,
                "raw_results": meeting.raw_results,
                "tasks_json": meeting.tasks_json,
                "meeting_summary": meeting.meeting_summary,
                "conclusion": meeting.conclusion,
            },
        }
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Get Meeting Detail Error")
        return {"status": "error", "message": str(e)}
_logger = ActivityLogger(prefix="VOICE", module="voice_app")

@frappe.whitelist(allow_guest=False)
def voice_to_task(existing_task=None, job_key=None):
    """Tạo Task từ giọng nói — chạy đồng bộ, trả kết quả trực tiếp qua HTTP."""
    if 'file' not in frappe.request.files:
        frappe.throw("Thiếu file âm thanh")

    audio_file = frappe.request.files['file']
    if existing_task and isinstance(existing_task, str):
        pass  # keep as string, parsed in _voice_to_task_async

    from frappe.utils.file_manager import save_file
    file_doc = save_file(audio_file.filename, audio_file.read(), None, None, is_private=1)
    file_path = frappe.get_site_path(file_doc.file_url.strip('/'))

    import time
    if not job_key:
        job_key = f"v2t_{frappe.session.user}_{int(time.time())}"
    session_id = frappe.get_request_header("X-App-Session-Id") or ""
    return _voice_to_task_async(
        file_path=file_path,
        existing_task=existing_task,
        user=frappe.session.user,
        session_id=session_id,
        job_key=job_key,
    )

@frappe.whitelist(allow_guest=False)
def get_context():
    if frappe.session.user == "Guest":
        frappe.throw("Vui lòng đăng nhập", frappe.AuthenticationError)

    import uuid
    dept = ""
    role = ""
    try:
        try:
            from ct_agent_hub.api.core import check_app_access
        except ImportError:
            from ct_agent_hub.api import check_app_access

        agents_data = check_app_access("2as_worksuite")
        user_depts = agents_data.get("user_departments", [])
        dept = ",".join(user_depts) if user_depts else ""
        role = agents_data.get("user_role", "")
    except ImportError:
        pass

    session_id = str(uuid.uuid4())
    session_name = _logger.create_session(session_id, dept=dept, role=role)

    return {
        "csrf_token": frappe.sessions.get_csrf_token(),
        "session_id": session_id,
        "session_name": session_name,
        "user": frappe.session.user,
        "full_name": frappe.utils.get_fullname(frappe.session.user) if frappe.session.user != "Guest" else "Guest"
    }

def _resolve_session(session_id: str) -> str:
    if not session_id:
        return ""
    try:
        rows = frappe.db.get_all(
            "VOICE Session",
            filters={"session_id": session_id},
            fields=["name"],
            limit=1,
            ignore_permissions=True,
        )
        return rows[0].name if rows else ""
    except Exception as exc:
        frappe.log_error(str(exc), "Resolve Voice Session Error")
        return ""

def _log_action(session_id: str, action: str, details: dict):
    if not session_id:
        return
    s_name = _resolve_session(session_id)
    if s_name:
        _logger.log_action(s_name, action, details)

def _voice_to_task_async(file_path, existing_task=None, user=None, session_id="", job_key=""):
    frappe.set_user(user)
    
    # ── Session & Action Logging ──
    session_name = _resolve_session(session_id)
    if not session_name:
        import uuid as _uuid
        session_name = _logger.create_session(str(_uuid.uuid4()))
    action_name = _logger.start_action(
        session_name,
        action_type="voice_to_task",
        input_summary="audio upload",
    )
    
    def send_progress(pct, msg):
        # In sync mode, progress goes to all so dev mode socket works
        frappe.publish_realtime("v2t_progress", {"progress": pct, "msg": msg, "job_key": job_key}, after_commit=False)
    
    send_progress(10, "Đang chuẩn bị file âm thanh...")
    
    try:
        # Chuyển đổi sang WAV
        wav, err = convert_to_wav(file_path)
        if err:
            frappe.publish_realtime("v2t_result", {"status": "error", "message": err}, user=user, after_commit=False)
            return {"status": "error", "message": err}

        send_progress(30, "Đang trích xuất văn bản (STT)...")
        segments, _raw_words, full_text, err, _prompt_tokens, _completion_tokens = call_gemini_stt(
            chunks_info=[{
                "name": "",
                "idx": 0,
                "wav": wav,
                "offset": 0,
                "mappings": [],
                "status": "Pending",
            }],
            language="vi",
        )
        if err:
            frappe.publish_realtime("v2t_result", {"status": "error", "message": err}, user=user, after_commit=False)
            return {"status": "error", "message": err}
            
        # Xóa file wav tạm
        if os.path.exists(wav): 
            os.remove(wav)

        if not full_text.strip():
            return {"status": "error", "message": "Không thể trích xuất văn bản từ âm thanh."}

        # Lấy danh sách dự án và nhân viên từ Worksuite
        from voice_app.constants import get_worksuite_url, get_worksuite_token
        BASE_URL = get_worksuite_url()

        from voice_app.constants import get_openai_api_key
        OPENAI_API_KEY = get_openai_api_key()
        from openai import OpenAI
        from datetime import datetime, timedelta
        from voice_app.utils.activity_logger import Timer

        # Load worksuite credentials from Voice App Settings
        try:
            _vas = frappe.get_doc("Voice App Settings")
            WS_EMAIL = _vas.worksuite_email or ""
            WS_PASSWORD = _vas.get_password("worksuite_password") or ""
        except Exception as exc:
            frappe.log_error(str(exc), "Load Worksuite Credentials Error")
            WS_EMAIL = ""
            WS_PASSWORD = ""

        projects = []
        employees = []
        try:
            session = requests.Session()
            login_resp = session.post(
                f"{BASE_URL}/api/method/login",
                json={"usr": WS_EMAIL, "pwd": WS_PASSWORD},
                timeout=30,
            )
            if login_resp.status_code == 200:
                # Lấy CSRF token
                csrf_token = None
                try:
                    r = session.get(f"{BASE_URL}/api/method/frappe.utils.get_csrf_token", timeout=5)
                    if r.status_code == 200:
                        csrf_token = r.json().get("message") or session.cookies.get("csrf_token")
                except Exception as exc:
                    frappe.log_error(str(exc), "Fetch Worksuite CSRF Token Error")
                if not csrf_token: 
                    csrf_token = session.cookies.get("csrf_token")
                if csrf_token:
                    session.headers.update({
                        "X-Frappe-CSRF-Token": csrf_token,
                        "X-Frappe-Site-Name":  BASE_URL.replace("https://", "").replace("http://", ""),
                    })

                # Lấy danh sách Projects active
                proj_resp = session.get(
                    f"{BASE_URL}/api/resource/Project",
                    params={"fields": '["name", "project_name"]', "limit_page_length": 5000},
                    timeout=30,
                )
                if proj_resp.status_code == 200:
                    projects = proj_resp.json().get("data", [])

                # Lấy danh sách Employees active từ cache thay vì gọi API User
                employees = get_cached_employees()
        except Exception as ex:
            frappe.log_error(str(ex), "Fetch Projects/Employees Error in Voice to Task")

        current_user_email = frappe.session.user
        current_employee = None
        for e in employees:
            if e.get("user_id") == current_user_email:
                current_employee = e
                break

        assignee_default = f"{current_employee.get('employee_name')} ({current_employee.get('name')})" if current_employee else ""

        # ── Limit list size to avoid prompt overflow ──
        projects = projects[:100]
        employees = employees[:100]

        # Gọi OpenAI để phân tích câu lệnh
        if not OPENAI_API_KEY:
            return {"status": "error", "message": "Thiếu OPENAI_API_KEY"}

        client = OpenAI(api_key=OPENAI_API_KEY)
        
        now = datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        current_day_of_week = now.strftime("%A")
        
        days_vi = {
            "Monday": "Thứ Hai",
            "Tuesday": "Thứ Ba",
            "Wednesday": "Thứ Tư",
            "Thursday": "Thứ Năm",
            "Friday": "Thứ Sáu",
            "Saturday": "Thứ Bảy",
            "Sunday": "Chủ Nhật"
        }
        day_vi = days_vi.get(current_day_of_week, current_day_of_week)

        # Phân tích existing_task gửi từ frontend nếu có
        parsed_existing = None
        if existing_task:
            try:
                parsed_existing = json.loads(existing_task)
            except Exception as e:
                frappe.log_error(f"Error parsing existing_task: {str(e)}", "Voice to Task JSON Parse Error")

        prompt = f"""
Bạn là trợ lý AI chuyên nghiệp giúp trích xuất và tinh chỉnh thông tin tạo nhiệm vụ (Task) từ đoạn hội thoại/giọng nói.
Hôm nay là {day_vi}, ngày {current_date_str} (định dạng YYYY-MM-DD).

Thông tin Người đang tạo Task (Current User):
- Tên: {current_employee.get('employee_name') if current_employee else 'Không rõ'}
- Email/ID: {current_user_email}
- Chức vụ: {current_employee.get('designation') if current_employee and current_employee.get('designation') else 'Không rõ'}

Hãy đọc đoạn văn bản được chuyển từ giọng nói sau đây:
Văn bản bổ sung mới: "{full_text}"

{"Thông tin Task hiện tại đang có trước khi bổ sung: " + json.dumps(parsed_existing, ensure_ascii=False) if parsed_existing else "Đây là lượt khởi tạo Task đầu tiên."}

Danh sách các dự án khả dụng (Project List):
{json.dumps(projects, ensure_ascii=False)}

Danh sách nhân viên khả dụng (Employee List) để giao nhiệm vụ:
{json.dumps([{"employee_name": e.get("employee_name"), "name": e.get("name")} for e in employees], ensure_ascii=False)}

Yêu cầu nhiệm vụ:
1. Kết hợp thông tin mới từ "Văn bản bổ sung mới" vào "Thông tin Task hiện tại" để hoàn thiện hoặc cập nhật các trường dưới đây.
2. Các trường cần trả về trong JSON:
   - "task_name": Tên nhiệm vụ cốt lõi mà người nói muốn thực hiện. ĐẶC BIỆT CHÚ Ý: 
     + Người dùng có thể nói lộn xộn, tự đính chính trong lúc nói (ví dụ: "à không", "sửa lại là..."). Phải lấy quyết định cuối cùng của họ.
     + Nếu họ nói ngọng hoặc nhầm lẫn giữa "tên dự án" và "tên nhiệm vụ", hãy tự suy luận ngữ cảnh để tách ra Hành động/Công việc (Task) và Tên dự án.
     + Nếu không có hành động rõ ràng (chỉ nói "test" hoặc một cụm từ), hãy lấy cụm từ đó làm tên nhiệm vụ. TUYỆT ĐỐI không để trống, nếu mập mờ hãy tự tóm tắt thành 1 cụm động từ.
   - "project_id": So sánh tên dự án được nhắc tới trong hội thoại với danh sách dự án ở trên. Chọn "name" của dự án khớp nhất. Nếu không khớp bất kỳ dự án nào, trả về null (hoặc giữ nguyên dự án cũ từ thông tin Task hiện tại).
   - "project_name": Tên dự án được nói tới (nhớ cập nhật theo ý đính chính cuối cùng của người nói).
   - "assignee_display": So sánh tên người thực hiện được nhắc tới với danh sách nhân viên khả dụng. Nếu khớp, điền 'employee_name (name)'. LƯU Ý QUAN TRỌNG: Nếu người dùng xưng "tôi", "mình", hoặc KHÔNG nhắc tới ai thực hiện, hãy tự động lấy "Người đang tạo Task" ở trên làm người thực hiện (điền '{assignee_default if assignee_default else "null"}' nếu có thông tin, ngược lại để null). Nếu nhắc tới tên không có trong danh sách, điền tên đó. Nếu không nhắc tới và không có Người đang tạo Task, trả về null (hoặc giữ nguyên người cũ từ thông tin Task hiện tại).
   - "start_date": Ngày bắt đầu (định dạng YYYY-MM-DD). Tính toán dựa trên ngày hôm nay ({current_date_str}). Ví dụ: "ngày mai" là ngày {(now + timedelta(days=1)).strftime("%Y-%m-%d")}. Nếu không nhắc tới, mặc định lấy ngày hôm nay ({current_date_str}).
   - "end_date": Ngày kết thúc / Hạn chót (định dạng YYYY-MM-DD). Tính toán dựa trên ngày hôm nay ({current_date_str}). Nếu không nhắc tới, trả về null (hoặc giữ nguyên hạn chót cũ từ thông tin Task hiện tại).
   - "task_type": Phân loại mục này là "task" (Nhiệm vụ cần làm) hay "noti" (Thông báo thông tin chung). Hãy xác định rõ dựa vào ngữ nghĩa (VD: giao việc là task, báo cáo trạng thái / thông tin là noti).
   - "description": Mô tả chi tiết nhiệm vụ (nếu có chi tiết hơn). Lọc bỏ các từ thừa, ậm ừ.
3. Kiểm tra tính đầy đủ của thông tin cốt lõi:
   - Một nhiệm vụ được coi là thiếu thông tin cốt lõi nếu:
     - Chưa xác định được dự án cụ thể (`project_id` là null hoặc "")
     - Hoặc chưa có người thực hiện (`assignee_display` là null hoặc "" hoặc chưa khớp với nhân viên nào dạng 'employee_name (name)')
     - Hoặc chưa có ngày kết thúc / hạn chót (`end_date` là null hoặc "")
   - "missing_fields": Hãy trả về danh sách các trường bị thiếu, có thể gồm: "project" (nếu thiếu dự án), "assignee" (nếu thiếu người thực hiện), "end_date" (nếu thiếu hạn chót). Lưu ý: Nếu `assignee_display` đã được gán tự động cho "Người đang tạo Task", thì KHÔNG bị tính là thiếu "assignee". Nếu không thiếu trường nào, trả về mảng rỗng [].
   - "clarification_question": Nếu có ít nhất một trường bị thiếu trong `missing_fields`, hãy viết một câu hỏi gợi ý rất ngắn gọn, tự nhiên, lịch sự bằng tiếng Việt để nhắc người dùng bổ sung các thông tin còn thiếu này qua giọng nói (Ví dụ: 'Nhiệm vụ này chưa có dự án cụ thể. Bạn muốn tạo task này cho dự án nào?' hoặc 'Nhiệm vụ này chưa có hạn chót. Hạn chót khi nào?'). Nếu thông tin đã đầy đủ hoặc không thiếu gì, trả về null.

Hãy trả về kết quả dưới dạng JSON duy nhất, KHÔNG chứa markdown (```json), KHÔNG giải thích thêm:
{{
  "task_name": "...",
  "task_type": "...",
  "project_id": "...",
  "project_name": "...",
  "assignee_display": "...",
  "start_date": "...",
  "end_date": "...",
  "description": "...",
  "missing_fields": [...],
  "clarification_question": "..."
}}
"""
        send_progress(60, "Đang phân tích ý định (AI)...")
        with Timer() as t:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
        send_progress(90, "Hoàn thiện dữ liệu...")
        parsed_data = json.loads(response.choices[0].message.content.strip())
        if "task_type" in parsed_data and parsed_data["task_type"]:
            loai_raw = str(parsed_data["task_type"]).lower()
            parsed_data["task_type"] = "noti" if "noti" in loai_raw or "thông báo" in loai_raw else "task"
        usage = response.usage
        p_tok = usage.prompt_tokens if usage else 0
        c_tok = usage.completion_tokens if usage else 0

        # ── AI Call Log ──
        _logger.log_ai_call(
            session_name, action_name,
            call_type="voice_to_task", ai_model="gpt-4o",
            prompt_tokens=p_tok, completion_tokens=c_tok,
            duration_seconds=t.elapsed, status="success",
        )
        _logger.finish_action(
            action_name, status="success",
            output_summary=f"task={parsed_data.get('task_name','')}",
            ai_model="gpt-4o",
            prompt_tokens=p_tok, completion_tokens=c_tok,
            duration_seconds=t.elapsed,
        )

        result_data = {
            "status": "success",
            "job_key": job_key,
            "transcript": full_text,
            "task": parsed_data,
            "projects": projects,
            "employees": employees
        }
        frappe.publish_realtime("v2t_result", result_data, after_commit=False)
        return result_data

    except Exception as e:
        frappe.log_error(traceback.format_exc(), "Voice to Task Error")
        _logger.finish_action(action_name, status="failed", error_message=str(e)[:500])
        frappe.publish_realtime("v2t_result", {"status": "error", "message": str(e), "job_key": job_key}, after_commit=False)
        return {"status": "error", "message": str(e)}
    finally:
        # ── Cleanup temp files ──
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass




@frappe.whitelist(allow_guest=False)
def resume_transcription(meeting_name):
    try:
        meeting_doc = frappe.get_doc("Voice Meeting", meeting_name)
        if not _can_access_meeting(meeting_doc.owner):
            frappe.throw("Không có quyền tiếp tục xử lý meeting này", frappe.PermissionError)

        if meeting_doc.status not in ["Error", "Partial Error"]:
            return {"status": "error", "message": "Chỉ có thể tiếp tục với meeting có trạng thái Lỗi hoặc Lỗi một phần."}
        
        frappe.db.set_value("Voice Meeting", meeting_name, {"status": "Processing", "error_message": ""})
        frappe.db.commit()
       
        # Get attached audio
        files = frappe.get_all("File", filters={"attached_to_doctype": "Voice Meeting", "attached_to_name": meeting_name}, fields=["file_url"])
        if not files:
            return {"status": "error", "message": "Không tìm thấy file âm thanh đính kèm."}
            
        file_url = files[0].file_url
        site_path = frappe.utils.get_site_path()
        if file_url.startswith('/private'):
            local_path = os.path.join(site_path, 'private', 'files', file_url.split('/')[-1])
        else:
            local_path = os.path.join(site_path, 'public', 'files', file_url.split('/')[-1])
            
        if not os.path.exists(local_path):
            return {"status": "error", "message": "File âm thanh không tồn tại trên hệ thống."}
            
        # Re-enqueue transcription
        frappe.db.set_value("Voice Meeting", meeting_name, "status", "Processing")
        frappe.db.commit()
        
        frappe.enqueue(
            _transcribe_audio_async,
            queue='long',
            timeout=7200,
            job_id=f"voice-transcribe-{meeting_name}",
            deduplicate=False,
            file_path=local_path,
            file_url=file_url,
            language=meeting_doc.get("language") or "vi",
            filter_speakers=meeting_doc.get("filter_speakers"),
            meeting_name=meeting_name,
            stt_mode="google",
            num_speakers=meeting_doc.get("num_speakers"),
            custom_vocabulary=meeting_doc.get("custom_vocabulary") or ""
        )
        
        return {"status": "processing", "meeting_name": meeting_name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "resume_transcription_error")
        if meeting_name and frappe.db.exists("Voice Meeting", meeting_name):
            frappe.db.set_value(
                "Voice Meeting",
                meeting_name,
                {"status": "Error", "error_message": str(e)},
            )
            frappe.db.commit()
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=False)
def undo_mapping(meeting_name):
    try:
        meeting_doc = frappe.get_doc("Voice Meeting", meeting_name)
        if not _can_access_meeting(meeting_doc.owner):
            frappe.throw("Không có quyền hoàn tác mapping meeting này", frappe.PermissionError)

        if not meeting_doc.original_raw_results:
            return {"status": "error", "message": "Không có dữ liệu gốc để hoàn tác."}
            
        frappe.db.set_value("Voice Meeting", meeting_name, "raw_results", meeting_doc.original_raw_results)
        frappe.db.commit()
        
        return {"status": "success", "results": json.loads(meeting_doc.original_raw_results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=False)
def get_global_vocabulary():
    try:
        vocab = frappe.db.get_single_value("Voice App Settings", "global_vocabulary")
        return {"status": "success", "message": vocab or ""}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=False)
def save_global_vocabulary(vocabulary):
    try:
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw("Không có quyền cập nhật global vocabulary", frappe.PermissionError)

        frappe.db.set_value("Voice App Settings", None, "global_vocabulary", vocabulary)
        frappe.db.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=False)
def export_dynamic_docx(meeting_name):
    from voice_app.docx_utils import save_to_docx
    from frappe.utils.file_manager import save_file
    import os
    import time
    try:
        meeting = frappe.get_doc("Voice Meeting", meeting_name)
        if not _can_access_meeting(meeting.owner):
            return {"status": "error", "message": "Không có quyền xuất meeting này"}
        
        raw_results = []
        if meeting.raw_results:
            raw_results = json.loads(meeting.raw_results)
            
        results = []
        for r in raw_results:
            if isinstance(r, dict):
                results.append((r.get("start"), r.get("end"), r.get("speaker"), r.get("text")))
            else:
                # Fallback for list/tuple format: [start, end, speaker, text]
                results.append(tuple(r))
            
        tasks = []
        if meeting.tasks_json:
            tasks = json.loads(meeting.tasks_json)
            
        # Try to get designations
        speaker_roles = {}
        try:
            raw_employees = get_cached_employees()
            for e in raw_employees:
                emp_name = (e.get("employee_name") or "").strip()
                desg = (e.get("designation") or "").strip()
                if emp_name and desg:
                    speaker_roles[emp_name.lower()] = desg
        except Exception as exc:
            frappe.log_error(str(exc), "Export DOCX Speaker Roles Error")

        start_time = meeting.date if meeting.date else ""
        
        docx_filename = save_to_docx(
            results,
            title=meeting.title,
            speaker_roles=speaker_roles,
            start_time=start_time,
            end_time="",
            location=meeting.location or "",
            chairperson=meeting.chairperson or "",
            meeting_summary=meeting.meeting_summary,
            conclusion=meeting.conclusion,
            tasks=tasks
        )
        
        with open(docx_filename, "rb") as f:
            filename = f"{meeting.name}_Minute_{int(time.time())}.docx"
            file_doc = save_file(filename, f.read(), "Voice Meeting", meeting.name, is_private=0)
            file_doc = _ensure_file_attachment(file_doc.file_url, "Voice Meeting", meeting.name, file_name=filename, is_private=0) or file_doc
            
        if os.path.exists(docx_filename):
            os.remove(docx_filename)
            
        return {"status": "success", "file_url": file_doc.file_url}
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "export_dynamic_docx Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=False)
def save_meeting_draft(meeting_name, summary=None, conclusion=None, tasks_json_str=None):
    if not meeting_name:
        frappe.throw("Thiếu meeting_name")
        
    if not frappe.db.exists("Voice Meeting", meeting_name):
        frappe.throw(f"Không tìm thấy cuộc họp {meeting_name}")
        
    doc = frappe.get_doc("Voice Meeting", meeting_name)
    if not _can_access_meeting(doc.owner):
        frappe.throw("Không có quyền chỉnh sửa meeting này", frappe.PermissionError)
    update_dict = {}
    if summary is not None:
        update_dict["meeting_summary"] = summary
    if conclusion is not None:
        update_dict["conclusion"] = conclusion
    if tasks_json_str is not None:
        update_dict["tasks_json"] = tasks_json_str
        
    if update_dict:
        frappe.db.set_value("Voice Meeting", meeting_name, update_dict, update_modified=False)
        frappe.db.commit()
    
    return {"status": "success", "message": "Đã lưu bản nháp thành công"}

def debug_clustering():
    import json
    import numpy as np
    from scipy.spatial.distance import cosine
    
    meeting = frappe.get_all("Voice Meeting", order_by="creation desc", limit=1)[0]
    doc = frappe.get_doc("Voice Meeting", meeting.name)
    if not doc.original_raw_results:
        print("No original_raw_results found!")
        return

    results = json.loads(doc.original_raw_results)
    segments = results if isinstance(results, list) else results.get("segments", [])

    spk_embeddings = {}
    strangers = set()
    for seg in segments:
        spk = seg.get("speaker_id")
        emb = seg.get("embedding")
        if spk and emb and spk.startswith("c"):
            strangers.add(spk)
            if spk not in spk_embeddings:
                spk_embeddings[spk] = np.array(emb)

    print(f"Found {len(spk_embeddings)} speakers.")

    def get_chunk_idx(s):
        try:
            return int(s.split("_")[0][1:])
        except (ValueError, TypeError, IndexError):
            return -1

    valid_strangers = list(strangers)
    valid_strangers.sort()

    groups = []
    for spk in valid_strangers:
        chunk_idx = get_chunk_idx(spk)
        emb = spk_embeddings[spk]
        
        best_sim = -1
        best_group_idx = -1
        
        print(f"\nEvaluating {spk} (Chunk {chunk_idx})")
        for i, grp in enumerate(groups):
            if any(get_chunk_idx(member) == chunk_idx for member in grp):
                print(f"  Group {i} ({grp}): SKIPPED (Chunk constraint)")
                continue
                
            grp_emb = np.mean([spk_embeddings[m] for m in grp], axis=0)
            if np.linalg.norm(grp_emb) == 0 or np.linalg.norm(emb) == 0:
                sim = 0.0
            else:
                sim = 1 - cosine(emb, grp_emb)
                
            print(f"  Group {i} ({grp}): Similarity = {sim:.4f}")
            
            if sim > best_sim:
                best_sim = sim
                best_group_idx = i
                
        if best_sim >= 0.45:
            print(f"  --> Merged into Group {best_group_idx} (Best Sim = {best_sim:.4f})")
            groups[best_group_idx].append(spk)
        else:
            print(f"  --> Formed NEW Group {len(groups)}")
            groups.append([spk])

    print("\nFinal Groups:")
    for i, grp in enumerate(groups):
        print(f"Group {i}: {grp}")
