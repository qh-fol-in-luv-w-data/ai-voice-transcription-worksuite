---
title: "Authentication Authorization"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa authentication authorization cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Authentication method

Frontend calls `get_context()` to obtain CSRF token, generated app session id, user and full name. Requests attach `X-Frappe-CSRF-Token` and `X-App-Session-Id`.

Source:

- `voice_app/api.py` — `get_context()`
- `frontend/src/api.js`
- `frontend/src/utils/session.js`

### Authorization model

| Control | Evidence |
|---|---|
| API default requires login | `@frappe.whitelist(allow_guest=False)` |
| Guest denied | Several functions check `frappe.session.user == "Guest"` |
| Meeting history scoped to owner | `get_meeting_history()` filters `owner=frappe.session.user` |
| Meeting download owner check | `download_meeting_file()` |
| System Manager override for meeting access | `_can_access_meeting()` |
| DocType admin permissions | JSON permissions mostly System Manager |

MFA/password policy/account lock: handled by Frappe core; NOT FOUND custom policy.

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

