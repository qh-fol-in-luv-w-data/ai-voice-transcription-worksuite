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
import torch
# Disable NNPACK and MKLDNN which cause "could not create a primitive" on some CPUs
if hasattr(torch.backends, 'nnpack'):
    torch.backends.nnpack.enabled = False
if hasattr(torch.backends, 'mkldnn'):
    torch.backends.mkldnn.enabled = False
torch.set_num_threads(1)
import torchaudio
import soundfile as sf

def _sf_info(uri, *args, **kwargs):
    info = sf.info(uri)
    class AudioInfo:
        def __init__(self, sr, frames, channels):
            self.sample_rate = sr
            self.num_frames = frames
            self.num_channels = channels
    return AudioInfo(info.samplerate, info.frames, info.channels)

def _sf_load(uri, frame_offset=0, num_frames=-1, normalize=True, channels_first=True, **kwargs):
    frames = num_frames if num_frames > 0 else -1
    data, samplerate = sf.read(uri, start=frame_offset, frames=frames, dtype='float32', always_2d=True)
    tensor = torch.from_numpy(data)
    if channels_first:
        tensor = tensor.t()
    return tensor, samplerate

torchaudio.info = _sf_info
torchaudio.load = _sf_load

if not hasattr(torchaudio, 'set_audio_backend'):
    torchaudio.set_audio_backend = lambda x: None

import huggingface_hub
_orig_hf_hub_download = huggingface_hub.hf_hub_download
def _patched_hf_hub_download(*args, **kwargs):
    if 'use_auth_token' in kwargs:
        kwargs['token'] = kwargs.pop('use_auth_token')
    return _orig_hf_hub_download(*args, **kwargs)
huggingface_hub.hf_hub_download = _patched_hf_hub_download

from scipy.spatial.distance import cosine
from .constants import get_hf_token, SPEAKER_DB_PATH, SIMILARITY_THRESHOLD

# ── PIPELINE & MODELS (Lazy Load) ──────────────────────────────────────────
_pipeline = None
_embedding_model = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        import torch
        from pyannote.audio import Pipeline
        import functools
        _orig_load = torch.load
        torch.load = functools.partial(torch.load, weights_only=False)
        try:
            # Quay lại bản 3.1 để đạt độ chính xác tối đa
            _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=get_hf_token() or None)
            device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
            _pipeline = _pipeline.to(device)
            print(f"✅ Đã tải Diarization Pipeline (3.1) trên {device}")
        except Exception as e:
            print(f"Lỗi load diarization pipeline: {e}")
        finally:
            torch.load = _orig_load
    return _pipeline

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        import torch
        from pyannote.audio import Model, Inference
        import functools
        _orig_load = torch.load
        torch.load = functools.partial(torch.load, weights_only=False)
        try:
            model = Model.from_pretrained("pyannote/embedding", use_auth_token=get_hf_token() or None)
            if model is None:
                print("❌ Không thể tải model 'pyannote/embedding'.")
                return None
            device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
            _embedding_model = Inference(model, window="whole", device=device)
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            try:
                import frappe
                frappe.log_error(title="Pyannote Load Error", message=err_msg)
            except:
                pass
            print(f"Lỗi load embedding model: {err_msg}")
            raise e
        finally:
            torch.load = _orig_load
    return _embedding_model

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
