---
title: "Test Cases"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa test cases cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| TC ID | Req | Scenario | Preconditions | Steps | Expected | Status |
|---|---|---|---|---|---|---|
| TC-001 | FR-001 | Upload valid audio | Logged in | Upload file, poll status | Completed with transcript | Draft |
| TC-002 | FR-001 | Missing audio | Logged in | Call API no file | Error `Thiếu file âm thanh` | Draft |
| TC-003 | FR-002 | Duplicate upload | Existing completed meeting | Upload same file | Existing result returned | Draft |
| TC-004 | FR-003 | Enroll voice | Logged in, sample audio | Submit sample | `Voice Speaker` created | Draft |
| TC-005 | FR-004 | Reassign speaker | Own meeting | Change segment speaker | Results updated | Draft |
| TC-006 | FR-006 | Extract tasks | Completed meeting | Run extract and poll | DOCX/XLSX/tasks available | Draft |
| TC-007 | FR-006 | Empty transcript | Meeting no raw_results | Run extract | Error no content | Draft |
| TC-008 | FR-007 | Sync no tasks | Logged in | Submit empty list | Error message | Draft |
| TC-009 | AUTH | Access another meeting file | Two users | Download other's file | Permission denied | Draft |
| TC-010 | OBS | Session logging | Open app | Perform AI action | VOICE logs updated | Draft |

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

