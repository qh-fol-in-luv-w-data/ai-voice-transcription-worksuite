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
                        emb_list = json.loads(s.get("embedding"))
                        processed[s.get("speaker_name")] = {
                            "embedding": np.array(emb_list, dtype=np.float32),
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
            return None, 0.0, "", None
        
        best_name = "Người lạ"
        best_sim = 0.0
        best_email = ""
        best_user_info = None
        
        # If filter provided, only compare against allowed speakers
        candidates = self.speakers.items()
        if allowed_names:
            candidates = ((n, v) for n, v in self.speakers.items() if n in allowed_names)
        
        for name, info in candidates:
            sim = 1 - cosine(embedding, info["embedding"])
            if sim > best_sim:
                best_sim = sim
                if sim >= SIMILARITY_THRESHOLD:
                    best_name = name
                    best_email = info["email"]
                    best_user_info = info.get("user_info")
        
        return best_name, best_sim, best_email, best_user_info

def get_segment_embedding(wav_path: str, start: float, end: float):
    try:
        emb = _extract_embedding_subprocess(wav_path, start, end)
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

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=180,  # 3 phút timeout cho lần đầu load model
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Subprocess embedding thất bại (exit={result.returncode}):\n{result.stderr[-2000:]}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"Subprocess không trả về kết quả. stderr:\n{result.stderr[-2000:]}")

    embedding_list = json.loads(stdout)
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
