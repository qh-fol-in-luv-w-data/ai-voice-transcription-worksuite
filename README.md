# 2AS WorkSuite - AI Voice Transcription & Task Automation

Ứng dụng **AI Voice Transcription** là một phân hệ (App) được xây dựng trên nền tảng **Frappe Framework** kết hợp với **Vue.js 3**. Ứng dụng giúp chuyển đổi âm thanh cuộc họp thành văn bản (Speech-to-Text), tự động nhận diện người nói (Diarization), ứng dụng AI để tóm tắt/lọc hội thoại và tự động trích xuất các công việc (Tasks) để đồng bộ vào hệ thống CTERP (WorkSuite).

## Tính năng nổi bật

- **Chuyển đổi Giọng nói thành Văn bản (STT)**: ElevenLabs Scribe v2, tự động nhận dạng ngôn ngữ (tiếng Việt + tiếng Anh hỗn hợp).
- **Phân tách người nói (Diarization)**: Pyannote Speaker-Diarization-3.1 chạy local, không cần internet sau khi tải model lần đầu.
- **Nhận diện & So sánh giọng nói (Voice Enrollment)**: Enroll giọng từng người, hệ thống tự gán tên khi có cuộc họp mới.
- **Gán tên người lạ**: Khi phát hiện giọng chưa đăng ký, giao diện cho phép map tay và enroll tự động.
- **Trích xuất công việc tự động (Task Extraction)**: GPT-4o phân tích cuộc họp, phân công người thực hiện, thời hạn và đồng bộ lên ERP.
- **Xuất Biên bản họp**: File Word và Excel dựa theo biểu mẫu.
- **Lọc hội thoại bằng AI**: Xóa từ ậm ừ, lấp liếm để biên bản gọn, súc tích.

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.10+ |
| Frappe Bench | v15+ |
| Node.js | 18+ |
| torch / torchaudio | 2.x (đã test với 2.12 / 2.11) |
| PyTorch đặc biệt | CPU-only OK, GPU nếu muốn nhanh hơn |

---

## Cài đặt

### 1. Lấy app và cài vào site

```bash
cd path/to/frappe-bench

bench get-app https://github.com/ctg-ai-data/2as-worksuite.git --branch main

bench --site [tên_site] install-app voice_app
```

### 2. Cài đặt Python dependencies

```bash
# Từ thư mục frappe-bench
env/bin/pip install \
    pyannote.audio==3.1.1 \
    matplotlib \
    soundfile \
    speechbrain \
    scipy \
    elevenlabs \
    openai \
    python-docx \
    openpyxl
```

> **Lưu ý quan trọng về tương thích:** Hệ thống dùng `torchaudio >= 2.5` và `numpy >= 2.0` — các phiên bản này đã loại bỏ một số API cũ mà `pyannote.audio 3.1.x` cần. File `voice_app/_torchaudio_compat.py` xử lý tự động việc này, không cần downgrade.

### 3. Cấu hình biến môi trường

Tạo file `.env` tại `apps/voice_app/voice_app/.env`:

```env
OPENAI_API_KEY=sk-your-openai-api-key
ELEVENLABS_API_KEY=your-elevenlabs-api-key
HF_TOKEN=hf_your-huggingface-token
```

### 4. Tải model Pyannote về máy (chỉ làm 1 lần khi có internet)

Hệ thống dùng các model sau từ HuggingFace. Cần accept điều khoản và tải về cache local trước khi chạy offline:

**Bước 1 — Accept điều khoản** (đăng nhập HuggingFace, click Accept trên từng trang):
- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
- [pyannote/embedding](https://huggingface.co/pyannote/embedding)
- [pyannote/wespeaker-voxceleb-resnet34-LM](https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM)

**Bước 2 — Tải model về cache** (chạy 1 lần, cần internet + HF_TOKEN):

```bash
env/bin/python - << 'EOF'
import os
os.environ["HF_TOKEN"] = "hf_your-token-here"

# Tải Pipeline (kéo theo segmentation + wespeaker)
import huggingface_hub as hfhub
orig = hfhub.hf_hub_download
def patched(*a, **kw):
    kw.setdefault("token", os.environ.get("HF_TOKEN"))
    if "use_auth_token" in kw:
        kw["token"] = kw.pop("use_auth_token")
    return orig(*a, **kw)
hfhub.hf_hub_download = patched

import sys
sys.path.insert(0, "apps/voice_app/voice_app")
import _torchaudio_compat
from pyannote.audio import Pipeline, Model

Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                         use_auth_token=os.environ["HF_TOKEN"])
Model.from_pretrained("pyannote/embedding",
                      use_auth_token=os.environ["HF_TOKEN"])
print("Models downloaded OK")
EOF
```

Sau bước này, model được lưu tại `~/.cache/torch/pyannote/`. Từ đây server chạy **hoàn toàn offline** (`HF_HUB_OFFLINE=1` được bật tự động trong subprocess).

### 5. Cài đặt và chạy Frontend

```bash
cd apps/voice_app/frontend
npm install
npm run dev -- --host
```

Giao diện chạy tại `http://localhost:5174`.

### 6. Khởi động Backend (Frappe)

```bash
cd path/to/frappe-bench
bench start
```

Backend chạy tại `http://localhost:8000`.

---

## Kiến trúc Diarization

Để tránh xung đột giữa PyTorch và Gunicorn (fork + DNNL/NNPACK), toàn bộ AI chạy trong **subprocess riêng biệt**:

```
api.py (Gunicorn worker)
  ├── ElevenLabs STT  →  raw_words (word + timestamp + speaker_id)
  │
  ├── subprocess: diarize_audio.py  →  pyannote segments [{start, end, speaker}]
  │     └── _torchaudio_compat.py  (compatibility shims)
  │
  └── Re-assign: mỗi word → speaker pyannote dựa trên time overlap
        └── Re-group thành segments mới → trả về frontend
```

```
api.py (enroll / identify)
  └── subprocess: extract_embedding.py  →  embedding vector 512d
        └── _torchaudio_compat.py  (compatibility shims)
```

### File quan trọng trong `voice_app/`

| File | Mô tả |
|---|---|
| `api.py` | Frappe API endpoints chính |
| `speaker_manager.py` | SpeakerDB (lưu embedding) + `run_diarization_subprocess()` |
| `diarize_audio.py` | Subprocess chạy pyannote Speaker-Diarization-3.1 |
| `extract_embedding.py` | Subprocess trích xuất speaker embedding |
| `_torchaudio_compat.py` | Compatibility shims cho torchaudio 2.x / NumPy 2.0 / PyTorch 2.6+ |
| `elevenlabs_client.py` | Gọi ElevenLabs Scribe v2 STT, trả về `raw_words` |
| `task_extractor.py` | GPT-4o: trích xuất task từ transcript |

---

## Compatibility Shims (`_torchaudio_compat.py`)

File này được import đầu tiên trong cả `diarize_audio.py` và `extract_embedding.py`. Nó vá các API bị xóa trong các phiên bản mới:

| Vấn đề | Phiên bản bỏ | Cách vá |
|---|---|---|
| `numpy.NaN` | NumPy 2.0 | `np.NaN = np.nan` |
| `torch.load(weights_only=True)` mặc định | PyTorch 2.6 | Force `weights_only=False` |
| `torchaudio.set/get_audio_backend()` | torchaudio 2.5 | Lambda shim |
| `torchaudio.load()` dùng torchcodec (cần FFmpeg) | torchaudio 2.11 | Thay bằng `soundfile` |
| `hf_hub_download(use_auth_token=...)` | huggingface_hub 0.21 | Redirect sang `token=` |
| `torchaudio.backend.common.AudioMetaData` | torchaudio 2.x | Stub class + sys.modules |

---

## Cấu hình nâng cao

### Ngưỡng nhận diện giọng nói (`SIMILARITY_THRESHOLD`)

Chỉnh trong `voice_app/constants.py`:

```python
SIMILARITY_THRESHOLD = 0.5  # 0.0–1.0, thấp hơn = dễ match hơn
```

### Số người nói tối đa (`MAX_SPEAKERS`)

Trong `voice_app/api.py` (tìm `MAX_SPEAKERS`):

```python
MAX_SPEAKERS = 10  # giới hạn số người trong cuộc họp
```

### Thời gian tối thiểu để auto-enroll giọng nói mới

Trong `voice_app/api.py` (hàm `map_and_enroll_speakers`):

```python
if seg_duration >= 2.0:  # giây, đủ dài để lấy mẫu chất lượng
```

---

## Troubleshooting

**`Could not create a primitive` khi khởi động**

Bình thường — lỗi này từ PyTorch DNNL/NNPACK trong Gunicorn worker. Hệ thống đã được thiết kế để chạy PyTorch trong subprocess riêng, nên lỗi này không ảnh hưởng đến chức năng.

**Diarization fallback về ElevenLabs**

Nếu log backend có `[Diarization] pyannote failed, fallback to ElevenLabs`, kiểm tra:
1. Model đã được tải về cache chưa (`ls ~/.cache/torch/pyannote/`)
2. Chạy thử thủ công: `env/bin/python apps/voice_app/voice_app/diarize_audio.py /path/to/test.wav "" 1 5`

**`ModuleNotFoundError: No module named 'matplotlib'`**

```bash
env/bin/pip install matplotlib
```

**Lỗi CORS**

Thêm vào `sites/[tên_site]/site_config.json`:

```json
{
  "allow_cors": "*"
}
```

**Giọng nói bị nhận nhầm người**

Tăng `SIMILARITY_THRESHOLD` lên `0.65`–`0.75`. Nếu không nhận ra ai, hạ xuống `0.4`–`0.5`.

---

## License

MIT
