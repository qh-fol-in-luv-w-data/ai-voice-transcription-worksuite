---
title: "Project Charter"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa project charter cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Tên dự án

2AS WorkSuite - AI Voice Transcription & Task Automation.

### Bối cảnh và vấn đề

Tổ chức cần chuyển đổi nội dung cuộc họp thành biên bản có cấu trúc, nhận diện người nói, trích xuất task/noti và đồng bộ về Worksuite/CTERP. Việc làm thủ công tốn thời gian, dễ bỏ sót người chịu trách nhiệm và deadline.

### Mục tiêu

| ID | Mục tiêu | Bằng chứng |
|---|---|---|
| OBJ-01 | Transcribe audio cuộc họp. | `voice_app/api.py` — `transcribe_audio()` |
| OBJ-02 | Nhận diện/enroll speaker. | `voice_app/api.py` — `enroll_voice()`, `map_and_enroll_speakers()` |
| OBJ-03 | Tạo DOCX/XLSX biên bản/task. | `voice_app/docx_utils.py`, `voice_app/api.py` — `_extract_tasks_async()` |
| OBJ-04 | Đồng bộ task sang ERP. | `voice_app/task_extractor.py` — `create_tasks_to_erp()` |
| OBJ-05 | Audit usage/AI calls. | `voice_app/utils/activity_logger.py` |

### Phạm vi

In scope: upload audio, STT, speaker identification, mapping/enrollment, transcript edit, task extraction, export, sync ERP, voice-to-task, activity logging.

Out of scope: NOT FOUND: billing, enterprise SSO customization, CI/CD automation, mobile native app.

### Deliverables và milestones

| Milestone | Deliverable | Acceptance |
|---|---|---|
| M1 | Cấu hình Frappe app và SPA | App load qua route `/aicenter/2as-worksuite`. |
| M2 | Voice transcription | `Voice Meeting` đạt status `Completed`. |
| M3 | Task extraction | Có `minute_docx`, `task_xlsx`, `tasks_json`. |
| M4 | ERP sync | API `sync_tasks_to_erp` trả success/report. |
| M5 | Handover | Tài liệu `docs/` được review. |

### Rủi ro cấp cao

- R-01: Phụ thuộc API key và quota Gemini/OpenAI/ElevenLabs.
- R-02: Audio dài gây backlog queue hoặc lỗi chunk.
- R-03: Speaker matching sai do sample ngắn hoặc threshold chưa hiệu chỉnh.
- R-04: Sensitive audio/transcript cần kiểm soát quyền truy cập.

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

