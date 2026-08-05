---
title: "Project Discovery"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-29"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Ghi nhận kết quả khảo sát repository trước khi sinh bộ tài liệu dự án.

## Phạm Vi

Bao phủ backend Frappe/Python, frontend Vue/Vite, DocType schema, API whitelist, cấu hình và tài liệu hiện có.

## Đối Tượng Sử Dụng

PM, BA, architect, developer, QA, DevOps, security reviewer và đội vận hành.

## Nội Dung Chi Tiết

### Tổng quan dự án

`voice_app` là Frappe app tên thương mại `2AS Worksuite`, phục vụ chuyển âm thanh cuộc họp thành transcript, nhận diện người nói, trích xuất task bằng AI và đồng bộ task sang Worksuite/CTERP.

Source:

- `README.md`
- `pyproject.toml`
- `voice_app/hooks.py`
- `frontend/package.json`

### Công nghệ phát hiện được

| Nhóm | Công nghệ | Bằng chứng |
|---|---|---|
| Backend | Python 3.10+, Frappe Framework v15+ | `pyproject.toml`, `README.md` |
| Frontend | Vue 3, Vite, Element Plus, Tailwind CSS | `frontend/package.json`, `frontend/src/App.vue` |
| Database | MariaDB qua Frappe DocType | `voice_app/voice_app/doctype/*/*.json` |
| Queue/Realtime | Frappe background jobs, Redis cache/realtime | `voice_app/api.py` — `frappe.enqueue()`, `frappe.publish_realtime()` |
| AI/STT | Google Gemini STT, ElevenLabs Scribe, OpenAI GPT-4o/GPT-4o-mini, Pyannote embedding | `voice_app/api.py`, `voice_app/gemini_stt_client.py`, `voice_app/task_extractor.py`, `voice_app/speaker_manager.py` |
| File export | DOCX, XLSX | `voice_app/docx_utils.py`, `voice_app/api.py` |
| Auth | Frappe session + CSRF | `voice_app/api.py` — `get_context()`, `frontend/src/api.js` |

### Cấu trúc repository

| Path | Vai trò |
|---|---|
| `voice_app/api.py` | Controller API chính cho transcription, task extraction, sync ERP, speaker mapping, voice-to-task, proctoring webhook. |
| `voice_app/speaker_manager.py` | Quản lý `Voice Speaker`, embedding, similarity matching. |
| `voice_app/task_extractor.py` | LangGraph/OpenAI flow đọc DOCX và trích xuất/sync task. |
| `voice_app/gemini_stt_client.py` | STT qua Gemini Files API/generate content. |
| `voice_app/elevenlabs_client.py` | STT qua ElevenLabs. |
| `voice_app/audio_utils.py` | Convert/chunk audio bằng ffmpeg/pydub. |
| `voice_app/docx_utils.py` | Sinh biên bản họp DOCX. |
| `frontend/src` | SPA Vue gồm các màn hình phân tích hội thoại, đăng ký giọng, voice task, lịch sử. |
| `voice_app/voice_app/doctype` | Schema DocType Frappe. |
| `docs` | Tài liệu hiện có và bộ tài liệu mới. |

### API chính

| API | Mục đích | Source |
|---|---|---|
| `POST /api/method/voice_app.api.transcribe_audio` | Upload audio và enqueue xử lý transcript. | `voice_app/api.py` — `transcribe_audio()` |
| `GET /api/method/voice_app.api.check_meeting_status` | Poll trạng thái transcript. | `voice_app/api.py` — `check_meeting_status()` |
| `POST /api/method/voice_app.api.extract_tasks` | Enqueue tạo DOCX/XLSX và task từ transcript. | `voice_app/api.py` — `extract_tasks()` |
| `GET /api/method/voice_app.api.check_extract_status` | Poll kết quả extract task. | `voice_app/api.py` — `check_extract_status()` |
| `POST /api/method/voice_app.api.sync_tasks_to_erp` | Đồng bộ task sang Worksuite. | `voice_app/api.py` — `sync_tasks_to_erp()` |
| `POST /api/method/voice_app.api.enroll_voice` | Đăng ký voice embedding cho user hiện tại. | `voice_app/api.py` — `enroll_voice()` |
| `POST /api/method/voice_app.api.voice_to_task` | Tạo/tinh chỉnh task trực tiếp từ voice. | `voice_app/api.py` — `voice_to_task()` |
| `POST /api/method/voice_app.api.resume_transcription` | Tiếp tục xử lý meeting lỗi hoặc lỗi một phần. | `voice_app/api.py` — `resume_transcription()` |
| `GET /api/method/voice_app.api.get_context` | Tạo app session và trả CSRF/session/user cho SPA. | `voice_app/api.py` — `get_context()` |

NOT FOUND: Không tìm thấy `proctoring_webhook()` trong source hiện tại.

### Database chính

| DocType | Vai trò |
|---|---|
| `Voice Meeting` | Cuộc họp, file audio, transcript, raw_results, DOCX/XLSX, summary, conclusion, tasks_json, token/cost STT. |
| `Voice Meeting Chunk` | Chunk audio khi STT dài, trạng thái từng chunk, raw_segments. |
| `Voice Speaker` | Speaker enrollment, email, user_info, embedding. |
| `Voice App Settings` | API key/config singleton cho Gemini, OpenAI, HuggingFace, embedding API và Worksuite. |
| `VOICE Session`, `VOICE Action Log`, `VOICE AI Call Log` | Audit, usage, token và AI call logging. |
| `Voice Task` | Local task entity rất mỏng, chưa thấy dùng như luồng chính. |

### Môi trường triển khai

- Local frontend: `npm run dev` trong `frontend/`, mặc định Vite.
- Backend: `bench start` trong Frappe Bench.
- Production: TODO: Cần xác nhận phương thức deploy thực tế.
- Scheduled job: daily `voice_app.api.cleanup_old_chunks` được khai báo trong `voice_app/hooks.py`; NOT FOUND: không thấy function này trong `voice_app/api.py`, cần kiểm tra runtime.
- Luồng STT thực tế: `voice_app/api.py` ép `stt_mode = "google"`; ElevenLabs client còn trong code nhưng endpoint `get_elevenlabs_info()` báo ElevenLabs STT đã tắt.

### Tài liệu hiện có

- `README.md`
- `implementation_plan.md`
- `security-scan copy.md`
- `docs/system_analysis_report.md`
- `docs/performance_optimization.md`
- `docs/performance_optimization_report.md`
- `docs/implementation_plan.md`
- `docs/Kiến trúc MapReduce.md`

### Điểm chưa rõ và rủi ro tài liệu

| Mục | Trạng thái |
|---|---|
| CI/CD | NOT FOUND |
| Docker/Kubernetes/Helm | NOT FOUND |
| Test framework chuẩn | NOT FOUND; chỉ có script test/debug rời rạc. |
| Production URL/SLA/RTO/RPO | TODO: Cần xác nhận |
| `cleanup_old_chunks` | Rủi ro drift giữa hook và source. |
| Secrets | Có DocType Settings và env var; tài liệu không ghi giá trị thật. |

### Kế hoạch sinh tài liệu

1. Tạo root docs: README, discovery, status, map, glossary, changelog.
2. Tạo tài liệu quản trị và nghiệp vụ dựa trên feature/API/DocType thực tế.
3. Tạo tài liệu UI/architecture/data/integration bằng Mermaid.
4. Tạo tài liệu kỹ thuật, bảo mật và AI prompt registry.
5. Tạo test/UAT/release/operations/runbook/checklist.

## Giả Định

- ASSUMPTION: Dự án được triển khai như một Frappe app trong Frappe Bench v15+ theo README hiện tại.
- ASSUMPTION: Các URL môi trường ngoài local cần được đội vận hành xác nhận.

## Vấn Đề Cần Xác Nhận

- TODO: Cần xác nhận owner tài liệu, người phê duyệt, SLA/SLO, RTO/RPO và môi trường production chính thức.
- NOT FOUND: Không tìm thấy CI/CD workflow, Dockerfile, Kubernetes manifest hoặc `.env.example` trong workspace hiện tại.
- TODO: Cần xử lý drift giữa code và schema: `Voice Meeting.status` trong code có dùng `Partial Error` nhưng schema chưa khai báo giá trị này.
- TODO: Cần rà soát duplicate function `reassign_speaker_from_segment()` trong `voice_app/api.py`; định nghĩa sau cùng là định nghĩa có hiệu lực runtime.


## Tài Liệu Liên Quan

- [README](README.md)
- [Document Map](DOCUMENT-MAP.md)
- [Project Discovery](00-PROJECT-DISCOVERY.md)

## Lịch Sử Thay Đổi

| Ngày | Phiên bản | Thay đổi | Tác giả |
|---|---:|---|---|
| 2026-07-28 | 0.1 | AI bổ sung tài liệu ban đầu từ source code. | Codex |
