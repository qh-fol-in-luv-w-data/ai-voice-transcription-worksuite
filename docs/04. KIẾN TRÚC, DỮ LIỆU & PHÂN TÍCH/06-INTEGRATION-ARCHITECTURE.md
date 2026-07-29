---
title: "Integration Architecture"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa integration architecture cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| ID | System | Direction | Protocol/Auth | Endpoint/source | Data exchanged | Retry/timeout | Owner |
|---|---|---|---|---|---|---|---|
| INT-001 | Google Gemini | Outbound | HTTPS API key | `gemini_stt_client.py` | Audio file, STT JSON | retry helpers, timeout TODO | DevOps |
| INT-002 | ElevenLabs | Outbound | HTTPS API key | `elevenlabs_client.py` | Audio, transcript, char balance | timeout TODO | DevOps |
| INT-003 | OpenAI | Outbound | HTTPS API key | `task_extractor.py`, `api.py` | Prompt, transcript, JSON | SDK exceptions | DevOps |
| INT-004 | HuggingFace/Pyannote | Outbound/local | HF token/cache | `speaker_manager.py`, `extract_embedding.py` | Model/embedding | subprocess timeout | AI/DevOps |
| INT-005 | Worksuite/CTERP | Outbound | Token/session | `task_extractor.py`, `api.py` | Employee, Project, Task | requests timeout 30 | Integration owner |
| INT-006 | Proctoring service | Inbound | Optional secret header | `proctoring_webhook()` | alert payload | 400/401 handling | Security |

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

