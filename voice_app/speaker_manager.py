import json
import os
import subprocess  # nosec B404 - subprocess calls use argv lists, local scripts, and timeouts.
import tempfile
import wave
from contextlib import suppress
from shutil import which
from urllib.parse import urlparse
# Fix "could not create a primitive" error in PyTorch on CPU environments (Linux/Docker)
os.environ["USE_NNPACK"] = "0"
os.environ["DNNL_PRIMITIVE_CACHE_CAPACITY"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import numpy as np
if not hasattr(np, 'NaN'):
    np.NaN = np.nan

# Note: We completely removed `torch` and `torchaudio` from this file!
# All embedding extraction runs in a completely separate subprocess (extract_embedding.py)
# This prevents the fatal PyTorch C++ runtime "could not create a primitive" error when Gunicorn forks workers.

from scipy.spatial.distance import cosine
from .constants import get_hf_token, SPEAKER_DB_PATH, SIMILARITY_THRESHOLD

def _get_embedding_api_url():
    url = (
        os.getenv("VOICE_EMBEDDING_API_URL")
        or os.getenv("EMBEDDING_API_URL")
        or ""
    ).strip()
    if not url:
        try:
            import frappe
            url = (
                frappe.conf.get("voice_embedding_api_url")
                or frappe.conf.get("embedding_api_url")
                or ""
            ).strip()
            if not url:
                doc = frappe.get_single("Voice App Settings")
                if doc.meta.has_field("embedding_api_url"):
                    url = (doc.get("embedding_api_url") or "").strip()
        except Exception as exc:
            print(f"Embedding API URL lookup failed: {exc}")
    if not url:
        url = "https://service.ctpai.vn/embedding"
    if not url.startswith(("https://", "http://")):
        url = f"https://{url}"
    parsed = urlparse(url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and parsed.hostname not in local_hosts:
        allow_insecure_http = os.getenv("VOICE_EMBEDDING_ALLOW_INSECURE_HTTP") == "1"
        if not allow_insecure_http:
            try:
                import frappe
                allow_insecure_http = bool(
                    frappe.conf.get("voice_embedding_allow_insecure_http")
                    or frappe.conf.get("allow_insecure_embedding_api_url")
                )
            except Exception:
                allow_insecure_http = False
        if not allow_insecure_http:
            raise ValueError(
                "Embedding API URL must use HTTPS for non-local hosts. "
                "Set voice_embedding_allow_insecure_http=1 only for trusted dev endpoints."
            )
    return url.rstrip("/")

# ── SPEAKER DATABASE ──────────────────────────────────────────────────────────
class SpeakerDB:
    def __init__(self):
        self.speakers = self._load_db()

    def _load_db(self):
        try:
            import frappe
            speakers = frappe.get_all("Voice Speaker", fields=["speaker_name", "email", "embedding", "user_info"])
            processed = {}
            for s in speakers:
                if s.get("embedding"):
                    try:
                        emb_val = s.get("embedding")
                        emb_list = json.loads(emb_val) if isinstance(emb_val, str) else emb_val
                        emb = np.array(emb_list, dtype=np.float32)
                        # L2 normalize để cosine similarity hoạt động đúng
                        norm = np.linalg.norm(emb)
                        if norm > 0:
                            emb = emb / norm
                        processed[s.get("speaker_name")] = {
                            "embedding": emb,
                            "email": s.get("email") or "Chưa cập nhật",
                            "user_info": s.get("user_info")
                        }
                    except Exception as e:
                        print(f"Error parsing embedding for {s.get('speaker_name')}: {e}")
            return processed
        except Exception as e:
            print(f"Lỗi load DB từ DocType: {e}")
            return {}

    def save_db(self):
        # Không cần lưu toàn bộ nữa, thêm từng speaker qua add_speaker
        pass

    def add_speaker(self, name, embedding, email="", user_info=None):
        import frappe
        try:
            # L2 normalize trước khi lưu
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            self.speakers[name] = {
                "embedding": embedding,
                "email": email or "Chưa cập nhật",
                "user_info": user_info
            }
            emb_json = json.dumps(embedding.tolist())
            user_info_json = json.dumps(user_info, ensure_ascii=False) if user_info else None
            
            # Cập nhật vào Frappe DB
            if frappe.db.exists("Voice Speaker", name):
                frappe.db.set_value("Voice Speaker", name, "embedding", emb_json)
                frappe.db.set_value("Voice Speaker", name, "email", email or "Chưa cập nhật")
                frappe.db.set_value("Voice Speaker", name, "user_info", user_info_json)
            else:
                doc = frappe.new_doc("Voice Speaker")
                doc.speaker_name = name
                doc.email = email or "Chưa cập nhật"
                doc.user_info = user_info_json
                doc.embedding = emb_json
                doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            print(f"Lỗi lưu Voice Speaker vào DB: {e}")

    def identify(self, embedding, allowed_names=None):
        if not self.speakers:
            return "Speaker", 0.0, "", None

        candidates = self.speakers.items()
        if allowed_names:
            candidates = ((n, v) for n, v in self.speakers.items() if n in allowed_names)

        scores = []
        for name, info in candidates:
            sim = 1 - cosine(embedding, info["embedding"])
            scores.append((name, sim, info["email"], info.get("user_info")))

        scores.sort(key=lambda x: x[1], reverse=True)
        top3 = ", ".join(f"{n}={s:.3f}" for n, s, _, _ in scores[:3])

        for name, sim, email, user_info in scores:
            if sim >= SIMILARITY_THRESHOLD:
                print(f"[Speaker] best='{name}'({sim:.3f}) threshold={SIMILARITY_THRESHOLD} | top3: [{top3}]")
                return name, sim, email, user_info

        best_sim = scores[0][1] if scores else 0.0
        print(f"[Speaker] best='Speaker'({best_sim:.3f}) threshold={SIMILARITY_THRESHOLD} | top3: [{top3}]")
        return "Speaker", best_sim, "", None

    def identify_ranked(self, embedding, allowed_names=None):
        """Trả về tất cả candidates >= threshold, sorted by score."""
        if not self.speakers:
            print(f"[Speaker] identify_ranked: Voice DB trống, không có ai để so sánh")
            return []

        candidates = list(self.speakers.items())
        if allowed_names:
            candidates = [(n, v) for n, v in candidates if n in allowed_names]

        all_scores = []
        for name, info in candidates:
            sim = 1 - cosine(embedding, info["embedding"])
            all_scores.append((name, sim, info["email"], info.get("user_info")))

        all_scores.sort(key=lambda x: x[1], reverse=True)
        top3 = ", ".join(f"{n}={s:.3f}" for n, s, _, _ in all_scores[:3])
        print(f"[Speaker] DB có {len(all_scores)} người | top3 scores: [{top3}] | threshold={SIMILARITY_THRESHOLD}")

        scores = [(n, s, e, u) for n, s, e, u in all_scores if s >= SIMILARITY_THRESHOLD]
        return scores

    def rank_all(self, embedding, allowed_names=None):
        """Return every candidate sorted by cosine score, without threshold filtering."""
        if not self.speakers:
            return []

        candidates = list(self.speakers.items())
        if allowed_names:
            candidates = [(n, v) for n, v in candidates if n in allowed_names]

        scores = []
        for name, info in candidates:
            sim = 1 - cosine(embedding, info["embedding"])
            scores.append((name, sim, info["email"], info.get("user_info")))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

# ── EMBEDDING CACHE (process-level, tránh gọi subprocess trùng lặp) ─────────
_embedding_cache: dict = {}   # key: (wav_path, start_rounded, end_rounded)
_CACHE_MAX = 64               # giới hạn tối đa số entry để tránh OOM

def get_segment_embedding(wav_path: str, start: float, end: float):
    """Trích xuất embedding có cache: cùng file+segment thì không gọi subprocess lại."""
    # Key = (path, start làm tròn 2 chữ số, end làm tròn 2 chữ số)
    cache_key = (wav_path, round(start, 2), round(end, 2))

    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    try:
        emb = _extract_embedding_subprocess(wav_path, start, end)
        if emb is not None:
            # L2 normalize về unit vector (cosine sim cần embedding normalized)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            # Giới hạn cache size (FIFO đơn giản)
            if len(_embedding_cache) >= _CACHE_MAX:
                oldest = next(iter(_embedding_cache))
                del _embedding_cache[oldest]
            _embedding_cache[cache_key] = emb
        return emb
    except Exception as e:
        print(f"Lỗi trích xuất embedding segment: {e}")
        return None

def _extract_embedding_subprocess(wav_path: str, start: float = None, end: float = None) -> "np.ndarray":
    """
    Chạy trích xuất embedding trong một subprocess hoàn toàn mới.
    Giải pháp dứt khoát cho lỗi 'could not create a primitive' của DNNL/NNPACK
    khi PyTorch bị fork bởi Gunicorn.
    """
    import sys
    from voice_app.constants import get_hf_token

    script_path = os.path.join(os.path.dirname(__file__), "extract_embedding.py")
    hf_token = get_hf_token() or ""
    python_exe = sys.executable

    args = [python_exe, script_path, wav_path, hf_token]
    if start is not None and end is not None:
        args.extend([str(start), str(end)])

    try:
        result = subprocess.run(  # nosec B603
            args,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        stderr_log = e.stderr[-2000:] if e.stderr else "None"
        stdout_log = e.stdout[-2000:] if e.stdout else "None"
        raise RuntimeError(f"Subprocess embedding timed out after 60s.\nSTDOUT:\n{stdout_log}\nSTDERR:\n{stderr_log}")

    if result.returncode != 0:
        raise RuntimeError(
            f"Subprocess embedding thất bại (exit={result.returncode}):\n{result.stderr[-2000:]}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"Subprocess không trả về kết quả. stderr:\n{result.stderr[-2000:]}")

    # stdout có thể chứa cả warning text lẫn JSON — tìm dòng JSON cuối cùng
    json_line = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith('['):
            json_line = line
            break
    if json_line is None:
        raise RuntimeError(f"Không tìm thấy JSON trong stdout:\n{stdout[:500]}")

    embedding_list = json.loads(json_line)
    return np.array(embedding_list)

def _extract_embeddings_from_files_remote(files_list: list, task: str = None) -> list:
    """
    Trích xuất embedding cho danh sách các file bằng cách gọi API external.
    files_list: list of dict [{"wav_path": str, "start": float, "end": float}, ...]
    Trả về: list các np.ndarray hoặc None
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock
    from contextlib import suppress

    api_url = _get_embedding_api_url()
    if not api_url:
        print("Chưa cấu hình embedding service, không có local fallback")
        return [None] * len(files_list)
    endpoint_url = f"{api_url}/extract"
    failure_notes = []
    failure_lock = Lock()

    def _remember_failure(message):
        with failure_lock:
            if len(failure_notes) < 8:
                failure_notes.append(str(message)[:1200])

    def _extract_one(index, item):
        wav_path = item.get("wav_path")
        start = item.get("start")
        end = item.get("end")
        post_path = wav_path
        cleanup_path = None
        
        if not wav_path or not os.path.exists(wav_path):
            _remember_failure(f"missing wav_path index={index} path={wav_path}")
            return index, None
            
        try:
            if start is not None and end is not None:
                try:
                    duration = float(end) - float(start)
                except Exception:
                    duration = 0
                if duration > 0:
                    from voice_app.audio_utils import extract_segment_ffmpeg

                    clip_path = extract_segment_ffmpeg(wav_path, float(start), float(end), padding=0.1)
                    if clip_path and os.path.exists(clip_path):
                        post_path = clip_path
                        cleanup_path = clip_path

            with open(post_path, "rb") as f:
                files = {
                    "file": (os.path.basename(post_path), f, "audio/wav")
                }
                data = {}
                # Nếu đã cắt clip local thì gửi nguyên clip ngắn, tránh upload
                # lại cả file meeting lớn cho từng segment.
                if cleanup_path is None and start is not None:
                    data["start"] = str(start)
                if cleanup_path is None and end is not None:
                    data["end"] = str(end)
                if task:
                    data["task"] = task
                    
                response = requests.post(endpoint_url, files=files, data=data, timeout=120)
                
                if response.status_code == 200:
                    result_json = response.json()
                    # Tùy thuộc vào cấu trúc trả về của API, giả sử trả về {'embedding': [...] } hoặc [...]
                    emb_data = result_json.get("embedding") if isinstance(result_json, dict) else result_json
                    
                    if isinstance(emb_data, list):
                        return index, np.array(emb_data)
                    msg = f"API không trả về embedding hợp lệ index={index}: {result_json}"
                    print(msg)
                    _remember_failure(msg)
                    return index, None
                msg = f"Lỗi API external index={index} status={response.status_code}: {response.text[:1000]}"
                print(msg)
                _remember_failure(msg)
                return index, None
        except Exception as e:
            msg = f"Lỗi khi gọi API external index={index} file={wav_path} start={start} end={end}: {e}"
            print(msg)
            _remember_failure(msg)
            return index, None
        finally:
            if cleanup_path:
                with suppress(FileNotFoundError):
                    os.remove(cleanup_path)

    final_results = [None] * len(files_list)
    try:
        import frappe
        max_workers = int(
            frappe.conf.get("voice_embedding_parallel_workers")
            or frappe.conf.get("embedding_parallel_workers")
            or os.getenv("VOICE_EMBEDDING_PARALLEL_WORKERS")
            or 4
        )
    except Exception:
        max_workers = int(os.getenv("VOICE_EMBEDDING_PARALLEL_WORKERS") or 4)
    max_workers = max(1, min(max_workers, 8, len(files_list) or 1))

    if len(files_list) <= 1 or max_workers == 1:
        for idx, item in enumerate(files_list):
            _, emb = _extract_one(idx, item)
            final_results[idx] = emb
    else:
        print(f"Embedding API parallel extraction: {len(files_list)} segments, workers={max_workers}")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_extract_one, idx, item): idx
                for idx, item in enumerate(files_list)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    _, emb = future.result()
                    final_results[idx] = emb
                except Exception as e:
                    print(f"Lỗi parallel embedding index={idx}: {e}")
                    final_results[idx] = None
            
    if files_list and not any(emb is not None for emb in final_results):
        print("Embedding API không trả về embedding nào, không có local fallback")
        if failure_notes:
            try:
                import frappe

                frappe.log_error(
                    "\n".join(failure_notes),
                    "Embedding API returned no embeddings",
                )
            except Exception:
                pass
        return final_results

    return final_results


def purify_speaker_group(segs, wav_path, db, min_segments=6, min_individual_score=0.35, task=None):
    """Gemini đôi khi gán nhầm 1 phần nhỏ lời của người KHÁC vào cùng 1
    speaker_id (VD: đo thực tế 1 meeting — 3/13 đoạn của 1 speaker_id thực ra
    là người khác, làm centroid gộp bị lai, giảm độ chính xác nhận diện).

    Probe từng đoạn đủ dài (>=1.5s) riêng lẻ, so với DB đã enroll. Nếu đa số
    đoạn cùng match rõ 1 người (>= min_individual_score), coi đó là "danh
    tính chính" của group — loại các đoạn match RÕ một người KHÁC ra khỏi
    group trước khi build centroid cuối. Không đủ dữ liệu / không có đa số
    rõ ràng thì giữ nguyên group, không đoán mò.

    Trả về (segs_đã_lọc, segs_bị_loại) — segs_bị_loại chỉ để log/debug.
    """
    if not db or not getattr(db, "speakers", None):
        return segs, []

    qualifying = [s for s in segs if (s.get("end", 0) - s.get("start", 0)) >= 1.5]
    if len(qualifying) < min_segments:
        return segs, []

    files_list = [{"wav_path": wav_path, "start": s["start"], "end": s["end"]} for s in qualifying]
    embs = _extract_embeddings_from_files_remote(files_list, task=task or "purify-probe")

    per_seg_best = []
    for seg, emb in zip(qualifying, embs):
        if emb is None:
            per_seg_best.append((seg, None))
            continue
        norm = np.linalg.norm(emb)
        emb_n = emb / norm if norm > 0 else emb
        ranked = db.rank_all(emb_n)
        best_name = ranked[0][0] if ranked and ranked[0][1] >= min_individual_score else None
        per_seg_best.append((seg, best_name))

    votes: dict = {}
    for _, name in per_seg_best:
        if name:
            votes[name] = votes.get(name, 0) + 1
    if not votes:
        return segs, []

    majority_name = max(votes.items(), key=lambda x: x[1])[0]
    if votes[majority_name] < len(qualifying) * 0.5:
        # Không ai chiếm đa số rõ ràng trong group -> không đủ tin cậy để lọc
        return segs, []

    dropped = [seg for seg, name in per_seg_best if name and name != majority_name]
    if not dropped:
        return segs, []

    dropped_ids = {id(s) for s in dropped}
    kept = [s for s in segs if id(s) not in dropped_ids]
    return kept, dropped


def enroll_new_speaker(name, wav_path, email="", user_info=None):
    """
    Trích xuất embedding từ file âm thanh mẫu và lưu vào database bằng cách gọi qua remote API.
    """
    from voice_app.audio_utils import get_duration
    if not which("ffmpeg"):
        return False
    if not wav_path or not os.path.isfile(str(wav_path)):
        return False
    
    # Dùng FFmpeg loại bỏ khoảng lặng (silence) để embedding không bị nhiễu
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        clean_wav = f.name
        
    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-af", "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB:stop_periods=-1:stop_duration=0.5:stop_threshold=-40dB",
        clean_wav
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)  # nosec B603
    except subprocess.TimeoutExpired:
        with suppress(FileNotFoundError):
            os.remove(clean_wav)
        return False
    if result.returncode != 0:
        with suppress(FileNotFoundError):
            os.remove(clean_wav)
        return False

    try:
        dur = get_duration(clean_wav)
    except (OSError, wave.Error, EOFError):
        dur = 3.0

    chunk_len = 3.0
    segments = []
    
    if dur > chunk_len:
        for s in np.arange(0, dur, chunk_len):
            e = min(s + chunk_len, dur)
            if e - s >= 1.0:
                segments.append({"wav_path": clean_wav, "start": float(s), "end": float(e)})
    else:
        segments.append({"wav_path": clean_wav, "start": 0.0, "end": dur})

    if not segments:
        with suppress(FileNotFoundError):
            os.remove(clean_wav)
        return False

    try:
        emb_res = _extract_embeddings_from_files_remote(
            segments,
            task="Đăng ký giọng nói"
        )
    finally:
        with suppress(FileNotFoundError):
            os.remove(clean_wav)
    
    valid_embs = [emb for emb in emb_res if emb is not None]
    if not valid_embs:
        return False

    avg_emb = np.mean(valid_embs, axis=0)

    db = SpeakerDB()
    db.add_speaker(name, avg_emb.tolist(), email=email, user_info=user_info)

    # Lưu lại audio gốc dùng để enroll — trước đây đường này không lưu, nên
    # về sau không cách nào audit lại được mẫu giọng đã enroll đúng người
    # chưa (không nghe lại được). Không để lỗi save_file làm hỏng cả lần
    # enroll — embedding vẫn đã lưu thành công ở trên.
    try:
        import time as _time
        import frappe
        from frappe.utils.file_manager import save_file
        if frappe.db and frappe.db.has_column("Voice Speaker", "sample_audio"):
            with open(wav_path, "rb") as f:
                file_doc = save_file(f"{name}_enroll_{int(_time.time())}.wav", f.read(), "Voice Speaker", name, is_private=1)
            frappe.db.set_value("Voice Speaker", name, "sample_audio", file_doc.file_url)
    except Exception as e:
        print(f"Lỗi lưu sample_audio khi enroll {name}: {e}")

    return True


# ── Nhận diện người nói KHÔNG dựa vào timestamp ────────────────────────────
# Cách cũ cắt mẫu giọng theo start/end của từng segment. Mà start/end thì do
# Gemini đoán hoặc forced-align suy ra — đo thực tế trên 1 file 80 phút, mốc
# này lệch tới hàng trăm giây, nên đoạn cắt ra chứa giọng người khác và mẫu
# giọng bị lai. Hệ quả: 2 speaker_id khác nhau cùng ra 1 tên, người còn lại
# biến mất khỏi biên bản.
#
# Ở đây bỏ hẳn timestamp khỏi khâu nhận diện: VAD chỉ ra chỗ nào thật sự có
# tiếng (biên đo trực tiếp trên sóng âm nên không thể lệch), cắt ra các cửa sổ
# ngắn, embed rồi gom cụm — mỗi cụm là một giọng. Timestamp vẫn dùng để hiển
# thị trong biên bản, nhưng sai mốc giờ không còn kéo theo gán nhầm người.

_VC_WIN_SEC = 3.0            # cửa sổ đủ ngắn để nằm gọn trong lời một người
_VC_MIN_WIN_SEC = 1.6        # ngắn hơn thì embedding không ổn định
_VC_MAX_WINDOWS = 240        # trần số lần gọi API embedding cho mỗi file
_VC_MIN_CLUSTER_WINDOWS = 5  # cụm nhỏ hơn coi là nhiễu, không phải người
_VC_MIN_SIMILARITY = 0.45    # dưới ngưỡng này thì để Speaker, không đoán bừa


def _vc_log(message, log_cb=None):
    if log_cb:
        log_cb(message)
    else:
        print(message)


def _vc_build_windows(wav_path, log_cb=None):
    """Cắt audio thành các cửa sổ ngắn nằm trong vùng VAD báo có tiếng nói."""
    from voice_app.gemini_stt_client import _vad_speech_intervals

    intervals = _vad_speech_intervals(wav_path)
    windows = []
    for start, end in intervals or []:
        pos = start
        while pos + _VC_MIN_WIN_SEC <= end:
            win_end = min(end, pos + _VC_WIN_SEC)
            if win_end - pos >= _VC_MIN_WIN_SEC:
                windows.append((round(pos, 2), round(win_end, 2)))
            pos += _VC_WIN_SEC

    if len(windows) > _VC_MAX_WINDOWS:
        # Lấy mẫu trải đều cả file thay vì cắt cụt phần đuôi, để người chỉ nói
        # ở nửa sau cuộc họp vẫn có mặt trong mẫu.
        step = len(windows) / _VC_MAX_WINDOWS
        windows = [windows[int(i * step)] for i in range(_VC_MAX_WINDOWS)]
    _vc_log(f"[VoiceCluster] {len(intervals or [])} vùng có tiếng → {len(windows)} cửa sổ", log_cb)
    return windows


def _vc_cluster(embeddings, n_speakers_hint):
    """Gom các cửa sổ thành cụm giọng.

    Số cụm lấy theo số speaker Gemini phát hiện (phần này Gemini làm chuẩn),
    cộng thêm 2 để chừa chỗ cho nhiễu/tiếng ồn — các cụm nhiễu đó nhỏ và sẽ bị
    loại ở bước sau, thay vì ép chúng lẫn vào giọng người thật.
    """
    from sklearn.cluster import AgglomerativeClustering

    n_clusters = max(2, min(len(embeddings) - 1, (n_speakers_hint or 2) + 2))
    return AgglomerativeClustering(
        n_clusters=n_clusters, metric="cosine", linkage="average"
    ).fit_predict(embeddings)


def _vc_match_clusters_to_db(clusters, db, min_similarity=_VC_MIN_SIMILARITY, log_cb=None):
    """Ghép cụm giọng với người trong DB theo kiểu 1-1.

    Dùng Hungarian chứ không phải "mỗi cụm tự chọn tên giống nhất": cách tự
    chọn cho phép hai cụm cùng nhận một tên, đúng lỗi đã gặp (hai speaker_id
    cùng ra 'chị Thuỷ' với 0.760 và 0.746, người thứ hai mất tích). Ràng buộc
    1-1 buộc thuật toán tối ưu tổng thể, nên cụm hợp lý hơn sẽ giữ được tên.
    """
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial.distance import cosine

    names = list(db.speakers.keys())
    cluster_ids = list(clusters.keys())
    if not names or not cluster_ids:
        return {}

    sim = np.array([
        [1 - cosine(clusters[c]["centroid"], np.asarray(db.speakers[n]["embedding"], dtype=float))
         for n in names]
        for c in cluster_ids
    ])

    rows, cols = linear_sum_assignment(-sim)
    assignment, stranger = {}, 0
    row_list = list(rows)
    for i, cluster_id in enumerate(cluster_ids):
        best_name, score = None, 0.0
        if i in row_list:
            j = cols[row_list.index(i)]
            score = float(sim[i][j])
            if score >= min_similarity:
                best_name = names[j]
        if best_name:
            info = db.speakers[best_name]
            assignment[cluster_id] = (best_name, score, info.get("email", ""), info.get("user_info"))
        else:
            stranger += 1
            assignment[cluster_id] = (f"Speaker {stranger}", score, "", None)
        greedy = names[int(np.argmax(sim[i]))]
        _vc_log(
            f"[VoiceCluster] cụm {cluster_id} ({clusters[cluster_id]['seconds']:.0f}s) → "
            f"{assignment[cluster_id][0]} ({score:.3f}); nếu chọn tham lam: {greedy}",
            log_cb,
        )
    return assignment


def _vc_map_speakers_to_clusters(segments, clusters, log_cb=None):
    """Ghép speaker_id của Gemini với cụm giọng, cũng theo kiểu 1-1.

    Không dùng mốc thời gian để so (đó chính là thứ không đáng tin). Thay vào
    đó ba dấu hiệu độc lập, cái nào cũng không cần biết câu nói nằm ở giây thứ
    mấy: ai nói nhiều hơn, ai cất tiếng trước, và ai nói câu dài hơn. Ba dấu
    hiệu cùng chỉ một hướng thì mới nhận; lệch nhau thì trả về rỗng để bên gọi
    dùng cách cũ, còn hơn gán sai tên vào biên bản.
    """
    from scipy.optimize import linear_sum_assignment

    words, seg_count, first_index = {}, {}, {}
    for index, seg in enumerate(segments):
        sid = seg.get("speaker_id") or seg.get("speaker") or "unknown"
        words[sid] = words.get(sid, 0) + len(str(seg.get("text") or "").split())
        seg_count[sid] = seg_count.get(sid, 0) + 1
        first_index.setdefault(sid, index)

    total_words = sum(words.values()) or 1
    # Người chỉ lọt vài chữ (Gemini gán nhầm lẻ tẻ) không đủ cơ sở để ghép.
    speakers = [s for s in sorted(words, key=lambda k: -words[k]) if words[s] / total_words >= 0.02]
    cluster_ids = list(clusters.keys())
    if not speakers or not cluster_ids:
        return {}

    total_seconds = sum(clusters[c]["seconds"] for c in cluster_ids) or 1.0
    votes = {s: {c: 0 for c in cluster_ids} for s in speakers}

    # 1. Ai nói nhiều, ai nói ít.
    for sid in speakers:
        share = words[sid] / total_words
        closest = min(cluster_ids, key=lambda c: abs(share - clusters[c]["seconds"] / total_seconds))
        votes[sid][closest] += 1

    # 2. Ai lên tiếng trước.
    for rank, sid in enumerate(sorted(speakers, key=lambda s: first_index[s])):
        by_time = sorted(cluster_ids, key=lambda c: clusters[c]["first_start"])
        if rank < len(by_time):
            votes[sid][by_time[rank]] += 1

    # 3. Ai nói câu dài, ai đáp câu ngắn.
    words_per_seg = {s: words[s] / max(1, seg_count[s]) for s in speakers}
    by_words = sorted(speakers, key=lambda s: -words_per_seg[s])
    by_turn = sorted(cluster_ids, key=lambda c: -clusters[c]["avg_turn"])
    for rank, sid in enumerate(by_words):
        if rank < len(by_turn):
            votes[sid][by_turn[rank]] += 1

    # Chốt bằng Hungarian để không có hai speaker_id cùng trỏ về một cụm.
    cost = np.array([[-votes[s][c] for c in cluster_ids] for s in speakers], dtype=float)
    rows, cols = linear_sum_assignment(cost)
    mapping = {}
    for i, j in zip(rows, cols):
        sid, cluster_id = speakers[i], cluster_ids[j]
        agree = votes[sid][cluster_id]
        _vc_log(f"[VoiceCluster] {sid} → cụm {cluster_id} ({agree}/3 dấu hiệu)", log_cb)
        if agree >= 2:
            mapping[sid] = cluster_id
    return mapping


def _vc_analyze(wav_path, segments, task=None, log_cb=None):
    """Gom cụm giọng rồi ghép từng cụm với speaker_id của Gemini.

    Trả về (clusters, mapping) với mapping là {speaker_id: cluster_id}; trả về
    ({}, {}) khi không đủ cơ sở kết luận. Tách riêng để cả khâu nhận diện lẫn
    khâu đăng ký giọng dùng chung một kết quả phân tích.
    """
    try:
        if not wav_path or not os.path.exists(wav_path) or not segments:
            return {}, {}

        windows = _vc_build_windows(wav_path, log_cb=log_cb)
        if len(windows) < _VC_MIN_CLUSTER_WINDOWS * 2:
            _vc_log("[VoiceCluster] quá ít cửa sổ, bỏ qua", log_cb)
            return {}, {}

        items = [{"wav_path": wav_path, "start": s, "end": e} for s, e in windows]
        embeddings = _extract_embeddings_from_files_remote(items, task=task or "Gom cụm giọng nói")

        pairs = [(w, np.asarray(e, dtype=float)) for w, e in zip(windows, embeddings) if e is not None]
        if len(pairs) < _VC_MIN_CLUSTER_WINDOWS * 2:
            _vc_log(f"[VoiceCluster] chỉ embed được {len(pairs)} cửa sổ, bỏ qua", log_cb)
            return {}, {}

        windows = [w for w, _ in pairs]
        matrix = np.stack([e / (np.linalg.norm(e) or 1.0) for _, e in pairs])

        hint = len({seg.get("speaker_id") or seg.get("speaker") for seg in segments})
        labels = _vc_cluster(matrix, hint)

        clusters = {}
        for label in sorted(set(labels)):
            idx = [i for i, l in enumerate(labels) if l == label]
            if len(idx) < _VC_MIN_CLUSTER_WINDOWS:
                continue
            centroid = matrix[idx].mean(axis=0)
            # Độ dài một lượt nói = chuỗi cửa sổ liền nhau cùng thuộc cụm này.
            ordered = sorted(idx, key=lambda i: windows[i][0])
            turns, run = [], 0.0
            for pos, i in enumerate(ordered):
                run += windows[i][1] - windows[i][0]
                is_last = pos == len(ordered) - 1
                if is_last or windows[ordered[pos + 1]][0] - windows[i][1] > _VC_WIN_SEC:
                    turns.append(run)
                    run = 0.0
            clusters[label] = {
                "centroid": centroid / (np.linalg.norm(centroid) or 1.0),
                "seconds": sum(windows[i][1] - windows[i][0] for i in idx),
                "first_start": min(windows[i][0] for i in idx),
                "avg_turn": (sum(turns) / len(turns)) if turns else 0.0,
                # Giữ lại chính các đoạn đã tạo nên cụm này: khi cần đăng ký
                # giọng, cắt thẳng từ đây là ra mẫu sạch, khỏi phải cắt theo
                # timestamp của segment (thứ đang lệch).
                "windows": [windows[i] for i in ordered],
            }

        if not clusters:
            _vc_log("[VoiceCluster] không có cụm nào đủ lớn", log_cb)
            return {}, {}
        _vc_log(f"[VoiceCluster] {len(clusters)} giọng thật từ {len(windows)} cửa sổ", log_cb)

        mapping = _vc_map_speakers_to_clusters(segments, clusters, log_cb=log_cb)
        if not mapping:
            _vc_log("[VoiceCluster] các dấu hiệu không thống nhất", log_cb)
            return clusters, {}
        return clusters, mapping
    except Exception as exc:
        _vc_log(f"[VoiceCluster] lỗi khi gom cụm: {exc!r}", log_cb)
        return {}, {}


def identify_speakers_by_voice_clustering(wav_path, segments, db, task=None, log_cb=None):
    """Trả về {speaker_id: (tên, điểm, email, user_info)}.

    Trả về rỗng nếu không đủ cơ sở kết luận — bên gọi tự quyết định xử lý.
    """
    if not db or not db.speakers:
        return {}
    clusters, mapping = _vc_analyze(wav_path, segments, task=task, log_cb=log_cb)
    if not clusters or not mapping:
        return {}
    names_by_cluster = _vc_match_clusters_to_db(clusters, db, log_cb=log_cb)
    return {sid: names_by_cluster[c] for sid, c in mapping.items() if c in names_by_cluster}


def build_voice_samples_by_clustering(wav_path, segments, task=None, log_cb=None, max_sample_sec=25.0):
    """Cắt sẵn mẫu giọng sạch cho từng speaker_id, phục vụ khâu đăng ký giọng.

    Trả về {speaker_id: đường_dẫn_wav}. Mẫu được ghép từ chính các đoạn đã tạo
    nên cụm giọng đó, nên không phụ thuộc start/end của segment — chỗ mà mốc
    thời gian lệch từng làm mẫu giọng lẫn người khác. Bên gọi tự xoá file khi
    dùng xong.
    """
    from voice_app.audio_utils import concat_speaker_segments

    clusters, mapping = _vc_analyze(wav_path, segments, task=task, log_cb=log_cb)
    if not clusters or not mapping:
        return {}

    samples = {}
    for speaker_id, cluster_id in mapping.items():
        cluster = clusters.get(cluster_id)
        if not cluster or not cluster.get("windows"):
            continue
        segs = [{"start": s, "end": e} for s, e in cluster["windows"]]
        sample = concat_speaker_segments(wav_path, segs, max_total_sec=max_sample_sec, min_seg_sec=1.5)
        if sample is None:
            sample = concat_speaker_segments(wav_path, segs, max_total_sec=max_sample_sec, min_seg_sec=0.0)
        if sample:
            samples[speaker_id] = sample
            _vc_log(
                f"[VoiceCluster] mẫu giọng {speaker_id}: {len(segs)} đoạn từ cụm {cluster_id}"
                f" ({cluster['seconds']:.0f}s)",
                log_cb,
            )
    return samples
