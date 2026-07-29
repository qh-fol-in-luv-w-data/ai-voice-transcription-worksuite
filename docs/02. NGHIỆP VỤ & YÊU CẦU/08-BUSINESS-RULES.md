---
title: "Business Rules"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa business rules cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Rule ID | Rule | Input | Condition | Processing | Output | Source |
|---|---|---|---|---|---|---|
| BR-001 | Guest không truy cập API chính | Session | `Guest` | Return/throw auth error | Error | `voice_app/api.py` |
| BR-002 | Meeting history chỉ trả meeting của owner | User | Authenticated | Filter owner | Meeting list | `get_meeting_history()` |
| BR-003 | Download chỉ cho owner | meeting_name | owner mismatch | Throw PermissionError | Denied | `download_meeting_file()` |
| BR-004 | Duplicate audio dùng content hash | File content | Hash exists | Reuse/resume | Existing/new meeting | `transcribe_audio()` |
| BR-005 | Speaker match theo threshold | Embedding | cosine >= threshold | Assign known speaker | Speaker name | `speaker_manager.py`, `constants.py` |
| BR-006 | Empty tasks không sync ERP | Tasks | list empty | Return error | Error | `sync_tasks_to_erp()` |

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

