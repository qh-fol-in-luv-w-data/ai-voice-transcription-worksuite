import os
# Fix "could not create a primitive" error in PyTorch on CPU environments (Linux/Docker)
os.environ["USE_NNPACK"] = "0"
os.environ["DNNL_PRIMITIVE_CACHE_CAPACITY"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import json
import numpy as np
if not hasattr(np, 'NaN'):
    np.NaN = np.nan

# Note: We completely removed `torch` and `torchaudio` from this file!
# All embedding extraction runs in a completely separate subprocess (extract_embedding.py)
# This prevents the fatal PyTorch C++ runtime "could not create a primitive" error when Gunicorn forks workers.

from scipy.spatial.distance import cosine
from .constants import get_hf_token, SPEAKER_DB_PATH, SIMILARITY_THRESHOLD

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
    import subprocess
    import sys
    import json
    from voice_app.constants import get_hf_token

    script_path = os.path.join(os.path.dirname(__file__), "extract_embedding.py")
    hf_token = get_hf_token() or ""
    python_exe = sys.executable

    args = [python_exe, script_path, wav_path, hf_token]
    if start is not None and end is not None:
        args.extend([str(start), str(end)])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=180,  # 3 phút timeout cho lần đầu load model
        )
    except subprocess.TimeoutExpired as e:
        stderr_log = e.stderr[-2000:] if e.stderr else "None"
        stdout_log = e.stdout[-2000:] if e.stdout else "None"
        raise RuntimeError(f"Subprocess embedding timed out after 180s.\nSTDOUT:\n{stdout_log}\nSTDERR:\n{stderr_log}")

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


def enroll_new_speaker(name, wav_path, email="", user_info=None):
    """
    Trích xuất embedding từ file âm thanh mẫu và lưu vào database.
    Dùng subprocess riêng để tránh lỗi DNNL/NNPACK trong môi trường Gunicorn.
    """
    embedding = _extract_embedding_subprocess(wav_path)

    db = SpeakerDB()
    db.add_speaker(name, embedding, email=email, user_info=user_info)
    return True
