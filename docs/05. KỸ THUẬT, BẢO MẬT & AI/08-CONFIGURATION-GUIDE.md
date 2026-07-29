---
title: "Configuration Guide"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa configuration guide cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Key | Source lookup | Required | Default | Sensitive | Notes |
|---|---|---|---|---|---|
| `OPENAI_API_KEY` / `openai_api_key` | Settings, site_config, env | For task AI | none | Yes | Do not expose frontend |
| `GEMINI_API_KEY` / `gemini_api_key` | Settings/env | For Gemini STT | none | Yes | |
| `GEMINI_MODEL` / `gemini_model` | Settings/env | Optional | code fallback varies | No | Duplicate functions exist in `constants.py`; review |
| `ELEVENLABS_API_KEY` | Settings/env | For ElevenLabs | none | Yes | |
| `HF_TOKEN` / `hf_token` | Settings/env | For Pyannote download/local | none | Yes | |
| `WORKSUITE_URL` | Settings/env | For ERP sync | `https://cterp.ctgroupvietnam.com` | No | URL normalized to HTTPS |
| `WORKSUITE_TOKEN` / `sync_api_token` | Settings/env | For ERP sync | none | Yes | |
| `GOOGLE_APPLICATION_CREDENTIALS` | Settings/env | Optional GCS | none | Path sensitive | |
| `GOOGLE_GCS_BUCKET` | Settings/env | Optional | `pai-stt` | No | |
| `VOICE_EMBEDDING_API_URL` | env/frappe conf/settings | Optional | empty/local subprocess | No/secret by network | HTTPS enforced for non-local |

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

