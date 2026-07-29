---
title: "Functional Requirements"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa functional requirements cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Req ID | Module | Requirement | Actor | Flow | Validation | Priority | Acceptance | Source | Status |
|---|---|---|---|---|---|---|---|---|---|
| FR-001 | Transcription | Upload audio và tạo `Voice Meeting`. | User | Upload -> enqueue -> poll | File required | High | Returns `processing`, later `success`. | `voice_app/api.py` — `transcribe_audio()` | Draft |
| FR-002 | Transcription | Resume/reuse uploaded file by content hash. | User | Duplicate file -> existing meeting | Hash match | Medium | Avoid duplicate processing when completed. | `voice_app/api.py` — `transcribe_audio()` | Draft |
| FR-003 | Speaker | Enroll current user's voice. | User | Upload sample -> embedding -> `Voice Speaker` | Login required | High | Speaker appears in enrolled list. | `voice_app/api.py` — `enroll_voice()` | Draft |
| FR-004 | Speaker | Map unknown speakers and auto-enroll. | User | Submit mappings -> update results | Meeting access | High | Speaker labels updated. | `voice_app/api.py` — `map_and_enroll_speakers()` | Draft |
| FR-005 | Meeting | Edit transcript/segments. | User | Submit results/text | Meeting owner/System Manager | Medium | `transcript` and JSON updated. | `voice_app/api.py` — `update_meeting_results()` | Draft |
| FR-006 | Task extraction | Generate DOCX/XLSX/task list. | User | `extract_tasks` -> poll | `meeting_name` required | High | Files and tasks saved. | `voice_app/api.py` — `_extract_tasks_async()` | Draft |
| FR-007 | ERP sync | Sync task list to Worksuite. | User | Submit tasks | Non-empty tasks | High | Returns report. | `voice_app/api.py` — `sync_tasks_to_erp()` | Draft |
| FR-008 | Voice-to-task | Create/refine task from voice. | User | Upload audio -> STT -> OpenAI JSON | File required | Medium | Returns parsed task. | `voice_app/api.py` — `voice_to_task()` | Draft |

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

