# 2AS WorkSuite - AI Voice Transcription & Task Automation

Ứng dụng **AI Voice Transcription** là một phân hệ (App) được xây dựng trên nền tảng **Frappe Framework** kết hợp với **Vue.js 3**. Ứng dụng giúp chuyển đổi âm thanh cuộc họp thành văn bản (Speech-to-Text), tự động nhận diện người nói (Diarization), ứng dụng AI để tóm tắt/lọc hội thoại và tự động trích xuất các công việc (Tasks) để đồng bộ vào hệ thống CTERP (WorkSuite).

## 🚀 Tính năng nổi bật

- **Chuyển đổi Giọng nói thành Văn bản (STT)**: Hỗ trợ tiếng Việt và nhiều ngôn ngữ khác.
- **Phân tách người nói (Diarization)**: Tự động nhận diện và gán tên người phát biểu dựa trên mẫu giọng nói (Voice Enrollment).
- **Trích xuất công việc tự động (Task Extraction)**: Dùng LLM (GPT-4o) để phân tích cuộc họp, phân công người thực hiện, thời hạn và đồng bộ lên ERP.
- **Xuất Biên bản họp**: Tạo file Word và Excel biên bản họp hoàn chỉnh dựa theo biểu mẫu.
- **Lọc hội thoại bằng AI**: Xóa bỏ các từ ậm ừ, lấp liếm để biên bản họp trở nên gọn gàng, súc tích.

---

## 🛠 Yêu cầu hệ thống

- **Backend**: Python 3.10+, Frappe Framework (Bench)
- **Frontend**: Node.js 18+, npm
- **API Keys**: OpenAI, ElevenLabs, HuggingFace (nếu cần)

---

## ⚙️ Hướng dẫn cài đặt và chạy ứng dụng

### 1. Cài đặt Backend (Frappe)

Ứng dụng này là một Frappe App. Bạn cần có sẵn một môi trường Frappe Bench.

```bash
# 1. Di chuyển vào thư mục bench của bạn
cd path/to/your/frappe-bench

# 2. Tải app về từ Github
bench get-app https://github.com/ctg-ai-data/2as-worksuite.git --branch main

# 3. Cài đặt app vào site hiện tại của bạn
bench --site [tên_site_của_bạn] install-app voice_app
```

### 2. Cấu hình Biến môi trường (.env)

Tạo một file `.env` trong thư mục gốc của app (`apps/voice_app/voice_app/.env`) hoặc thiết lập các biến môi trường trên hệ thống với các giá trị sau:

```env
OPENAI_API_KEY=sk-your-openai-api-key
ELEVENLABS_API_KEY=your-elevenlabs-api-key
WHISPER_URL=http://localhost:8080/inference # (Tùy chọn, nếu dùng local Whisper)
HF_TOKEN=hf_your-huggingface-token # (Bắt buộc để dùng AI nhận diện giọng nói)
```

**Hướng dẫn lấy HuggingFace Token (`HF_TOKEN`) để Phân biệt & So sánh giọng nói:**
Hệ thống sử dụng thư viện **Pyannote Audio** để tự động nhận diện và phân tách giọng nói. Quá trình tải model diễn ra tự động, nhưng bạn cần cấp quyền truy cập:
1. Đăng ký tài khoản tại [HuggingFace](https://huggingface.co/).
2. Truy cập vào trang của Model Diarization: [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) và nhấn **Accept Conditions**.
3. Truy cập vào trang của Model Embedding (dùng để so sánh đặc trưng giọng nói): [pyannote/embedding](https://huggingface.co/pyannote/embedding) và nhấn **Accept Conditions**.
4. Truy cập vào trang Model Phân đoạn: [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) và nhấn **Accept Conditions**.
5. Vào **Settings ➔ Access Tokens**, tạo một token mới (loại `Read`) và dán vào biến `HF_TOKEN` trong file `.env` như trên.
*(Khi khởi chạy lần đầu tiên, hệ thống sẽ tự động sử dụng token này để tải các model về máy)*.

### 3. Cài đặt và Chạy Frontend (Vue.js)

Giao diện người dùng được xây dựng hoàn toàn độc lập bằng Vue.js + Vite và nằm trong thư mục `frontend`.

```bash
# 1. Di chuyển vào thư mục frontend
cd apps/voice_app/frontend

# 2. Cài đặt các gói thư viện Node.js
npm install

# 3. Khởi động server Frontend
npm run dev -- --host
```

Sau khi chạy lệnh trên, giao diện web sẽ chạy tại: `http://localhost:5174` (hoặc cổng tương ứng hiển thị trên terminal).

### 4. Khởi động hệ thống (Chạy Backend)

Mở một terminal mới (giữ terminal frontend vẫn chạy), di chuyển vào thư mục bench và khởi động các dịch vụ Frappe:

```bash
cd path/to/your/frappe-bench
bench start
```

Backend Frappe thường sẽ chạy tại `http://localhost:8000`. Frontend sẽ tự động gọi API tới cổng 8000 này.

---

## 📖 Cấu trúc thư mục

- `voice_app/`: Chứa mã nguồn Python, API endpoints (`api.py`), cấu trúc DocType của Frappe.
- `voice_app/task_extractor.py`: Xử lý Logic AI, LangGraph, prompt OpenAI.
- `voice_app/docx_utils.py`: Logic xuất file Word (Biên bản họp).
- `frontend/`: Toàn bộ mã nguồn giao diện Vue 3 (Sử dụng Vite, Tailwind CSS, Shadcn-Vue).
- `public/files/template_v2.docx`: Biểu mẫu xuất file Word chuẩn.

---

## 🐛 Troubleshooting (Sửa lỗi thường gặp)

1. **Lỗi không kết nối được Backend**: Đảm bảo bạn đang mở cả `bench start` và `npm run dev`. Hãy kiểm tra URL gọi API trong `frontend/src/api.js`.
2. **Lỗi không có quyền (CORS)**: Nếu bạn chạy Frontend và Backend ở hai cổng khác nhau mà bị chặn CORS, hãy thêm cấu hình cho phép tên miền localhost trong file `site_config.json` của Frappe.
3. **Lỗi AI không phản hồi**: Kiểm tra lại file `.env` xem `OPENAI_API_KEY` đã được thiết lập đúng hay chưa.

## 📄 License
MIT
