---
title: "Use Cases"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa use cases cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Use Case ID | Name | Actor | Goal | Trigger | Preconditions | Postconditions | Related modules |
|---|---|---|---|---|---|---|---|
| UC-001 | Transcribe meeting | User | Tạo transcript | Upload audio | Logged in | `Voice Meeting` completed/error | API, Gemini/ElevenLabs, Audio |
| UC-002 | Review transcript | User | Sửa speaker/text | Open meeting | Own meeting | JSON/transcript updated | API, UI |
| UC-003 | Extract tasks | User | Tạo DOCX/XLSX/tasks | Click extract | Transcript available | Meeting analyzed | API, DOCX, OpenAI |
| UC-004 | Voice to task | User | Tạo task từ câu nói | Upload/record voice | Logged in | Parsed task returned | ElevenLabs, OpenAI |
| UC-005 | Proctoring alert | External service | Log alert count | Webhook POST | Optional secret valid | Cache/realtime event | API, Frappe cache |

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

