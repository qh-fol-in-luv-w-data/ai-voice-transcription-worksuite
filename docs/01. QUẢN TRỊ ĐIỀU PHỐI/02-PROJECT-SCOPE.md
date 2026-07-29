---
title: "Project Scope"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa project scope cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Scope boundaries

| Nhóm | In scope | Out of scope |
|---|---|---|
| Functional | Transcribe, speaker enroll/map, task extraction, export, sync ERP, voice-to-task. | Approval workflow phức tạp, mobile native. |
| Technical | Frappe API, DocType, queue, cache, Vue SPA. | Kubernetes/Helm vì NOT FOUND. |
| Data | `Voice Meeting`, `Voice Meeting Chunk`, `Voice Speaker`, `VOICE* Log`. | Data warehouse/reporting nâng cao. |
| Security | Frappe auth, CSRF, owner check cho meeting history/download. | MFA/password policy riêng vì dùng Frappe core. |

### Acceptance boundaries

- Transcript cần lưu được vào `Voice Meeting.transcript`.
- Raw segment JSON cần lưu trong `Voice Meeting.raw_results`.
- Task extraction không được ghi đè meeting của user khác; source có `_can_access_meeting()`.
- Secret không được đưa vào frontend hoặc tài liệu.

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

