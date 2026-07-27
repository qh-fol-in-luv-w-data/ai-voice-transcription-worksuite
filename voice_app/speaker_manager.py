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
        return ""
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

def _extract_embeddings_from_files_local(files_list: list) -> list:
    import sys
    from voice_app.constants import get_hf_token

    if not files_list:
        return []

    script_path = os.path.join(os.path.dirname(__file__), "extract_embedding.py")
    hf_token = get_hf_token() or ""
    python_exe = sys.executable

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
        json.dump(files_list, f)
        temp_file_path = f.name

    args = [python_exe, script_path, "", hf_token, "--files-list", temp_file_path]
    try:
        result = subprocess.run(  # nosec B603
            args,
            capture_output=True,
            text=True,
            timeout=max(300, 45 * len(files_list)),
        )
    except subprocess.TimeoutExpired:
        with suppress(FileNotFoundError):
            os.remove(temp_file_path)
        raise RuntimeError(f"Local batch embedding timed out for {len(files_list)} files.")
    finally:
        with suppress(FileNotFoundError):
            os.remove(temp_file_path)

    if result.returncode != 0:
        raise RuntimeError(
            f"Local batch embedding failed (exit={result.returncode}):\n{result.stderr[-2000:]}"
        )

    stdout = result.stdout.strip()
    json_line = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("["):
            json_line = line
            break
    if json_line is None:
        raise RuntimeError(f"Không tìm thấy JSON trong local batch stdout:\n{stdout[-2000:]}")

    results_list = json.loads(json_line)
    final_results = []
    for emb in results_list:
        final_results.append(None if emb is None else np.array(emb))
    return final_results

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
            return "Người lạ", 0.0, "", None

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
        print(f"[Speaker] best='Người lạ'({best_sim:.3f}) threshold={SIMILARITY_THRESHOLD} | top3: [{top3}]")
        return "Người lạ", best_sim, "", None

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

    api_url = _get_embedding_api_url()
    if not api_url:
        print("Chưa cấu hình embedding service, fallback sang local subprocess")
        return _extract_embeddings_from_files_local(files_list)
    endpoint_url = f"{api_url}/extract"
    final_results = []
    
    for item in files_list:
        wav_path = item.get("wav_path")
        start = item.get("start")
        end = item.get("end")
        
        if not wav_path or not os.path.exists(wav_path):
            final_results.append(None)
            continue
            
        try:
            with open(wav_path, "rb") as f:
                files = {
                    "file": (os.path.basename(wav_path), f, "audio/wav")
                }
                data = {}
                if start is not None:
                    data["start"] = str(start)
                if end is not None:
                    data["end"] = str(end)
                if task:
                    data["task"] = task
                    
                response = requests.post(endpoint_url, files=files, data=data, timeout=120)
                
                if response.status_code == 200:
                    result_json = response.json()
                    # Tùy thuộc vào cấu trúc trả về của API, giả sử trả về {'embedding': [...] } hoặc [...]
                    emb_data = result_json.get("embedding") if isinstance(result_json, dict) else result_json
                    
                    if isinstance(emb_data, list):
                        final_results.append(np.array(emb_data))
                    else:
                        print(f"API không trả về embedding hợp lệ: {result_json}")
                        final_results.append(None)
                else:
                    print(f"Lỗi API external (status {response.status_code}): {response.text}")
                    final_results.append(None)
        except Exception as e:
            print(f"Lỗi khi gọi API external cho {wav_path}: {e}")
            final_results.append(None)
            
    if files_list and not any(emb is not None for emb in final_results):
        print("Embedding API không trả về embedding nào, fallback sang local subprocess")
        return _extract_embeddings_from_files_local(files_list)

    return final_results

def _extract_embeddings_batch_subprocess(wav_path: str, segments_list: list) -> list:
    """
    Trích xuất embedding cho nhiều đoạn (batch) chỉ với 1 lần load model.
    segments_list: list of dict [{"start": float, "end": float}, ...]
    Trả về: list các np.ndarray hoặc None
    """
    import sys
    import tempfile
    from voice_app.constants import get_hf_token

    if not segments_list:
        return []

    script_path = os.path.join(os.path.dirname(__file__), "extract_embedding.py")
    hf_token = get_hf_token() or ""
    python_exe = sys.executable

    # Ghi segments ra file tạm
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
        json.dump(segments_list, f)
        temp_file_path = f.name

    args = [python_exe, script_path, wav_path, hf_token, "--segments-file", temp_file_path]

    try:
        result = subprocess.run(  # nosec B603
            args,
            capture_output=True,
            text=True,
            timeout=300,  # 5 phút timeout cho batch
        )
    except subprocess.TimeoutExpired as e:
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise RuntimeError("Batch subprocess embedding timed out after 300s.")
    
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)

    if result.returncode != 0:
        raise RuntimeError(
            f"Batch subprocess embedding thất bại (exit={result.returncode}):\n{result.stderr[-2000:]}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"Batch subprocess không trả về kết quả. stderr:\n{result.stderr[-2000:]}")

    json_line = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith('['):
            json_line = line
            break
    if json_line is None:
        raise RuntimeError(f"Không tìm thấy JSON trong stdout:\n{stdout[:500]}")

    results_list = json.loads(json_line)
    final_results = []
    for emb in results_list:
        if emb is None:
            final_results.append(None)
        else:
            final_results.append(np.array(emb))
    return final_results


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
    return True
