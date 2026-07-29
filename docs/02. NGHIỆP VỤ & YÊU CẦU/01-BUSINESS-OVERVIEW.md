---
title: "Business Overview"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa business overview cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Business context

Luồng chính là biến âm thanh họp thành tài sản vận hành: transcript, biên bản, danh sách task/noti và dữ liệu đồng bộ Worksuite.

### Business capabilities

| Capability | Mô tả | Source |
|---|---|---|
| Meeting transcription | Upload và xử lý audio meeting. | `voice_app/api.py` — `transcribe_audio()` |
| Speaker recognition | Enroll/match/map speaker. | `voice_app/speaker_manager.py`, `voice_app/api.py` |
| Meeting minutes | Xuất DOCX từ segments. | `voice_app/docx_utils.py` |
| Task extraction | OpenAI phân tích biên bản. | `voice_app/task_extractor.py` |
| ERP sync | Tạo task sang Worksuite/CTERP. | `voice_app/task_extractor.py` — `create_tasks_to_erp()` |
| Audit | Ghi session/action/AI call. | `voice_app/utils/activity_logger.py` |


```mermaid
flowchart TD
  A[User đăng nhập Frappe] --> B[SPA init get_context]
  B --> C[Upload audio]
  C --> D[transcribe_audio enqueue long job]
  D --> E[Convert WAV và chunk audio]
  E --> F[Gemini hoặc ElevenLabs STT]
  F --> G[Speaker embedding và identification]
  G --> H[Save Voice Meeting transcript/raw_results]
  H --> I[User review/edit/map speaker]
  I --> J[extract_tasks enqueue]
  J --> K[Generate DOCX và OpenAI extract tasks]
  K --> L[Save minute_docx/task_xlsx/tasks_json]
  L --> M[Optional sync_tasks_to_erp]
```

## Giả Định

- ASSUMPTION: Dự án được triển khai như một Frappe app trong Frappe Bench v15+ theo README hiện tại.
- ASSUMPTION: Các URL môi trường ngoài local cần được đội vận hành xác nhận.

## Vấn Đề Cần Xác Nhận

- TODO: Cần xác nhận owner tài liệu, người phê duyệt, SLA/SLO, RTO/RPO và môi trường production chính thức.
- NOT FOUND: Không tìm thấy CI/CD workflow, Dockerfile, Kubernetes manifest hoặc `.env.example` trong workspace hiện tại.

## Tài Liệu Liên Quan

- [Project Discovery](../00-PROJECT-DISCOVERY.md)
- [Document Map](../DOCUMENT-MAP.md)
- [API Specification](../05. KỸ THUẬT, BẢO MẬT & AI/03-API-SPECIFICATION.md)
- [Requirement Traceability Matrix](../02. NGHIỆP VỤ & YÊU CẦU/09-REQUIREMENT-TRACEABILITY-MATRIX.md)

## Lịch Sử Thay Đổi

| Ngày | Phiên bản | Thay đổi | Tác giả |
|---|---:|---|---|
| 2026-07-28 | 0.1 | AI bổ sung tài liệu ban đầu từ source code. | Codex |

