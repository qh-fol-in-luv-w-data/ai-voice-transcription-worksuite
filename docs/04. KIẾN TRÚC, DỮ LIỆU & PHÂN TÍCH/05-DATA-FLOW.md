---
title: "Data Flow"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa data flow cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Source | Destination | Transformation | Protocol | Frequency | Security | Error handling | Retention |
|---|---|---|---|---|---|---|---|
| Browser audio | Frappe File | save private file | HTTPS/FormData | User action | Auth+CSRF | Frappe throw/error | TODO |
| Audio file | Gemini/ElevenLabs | STT to segments | HTTPS API | Per meeting | API key | Error status | Provider policy TODO |
| Segments/audio | SpeakerDB | Embedding/match | local subprocess or HTTPS remote | Per meeting | token/HTTPS check | fallback/error log | Stored in Voice Speaker |
| Transcript | OpenAI | JSON tasks/summary | HTTPS API | Per extract | API key | cache error | Provider policy TODO |
| Tasks | Worksuite | Create/sync Task | HTTPS API | User action | token/session | report/error | External policy TODO |

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

