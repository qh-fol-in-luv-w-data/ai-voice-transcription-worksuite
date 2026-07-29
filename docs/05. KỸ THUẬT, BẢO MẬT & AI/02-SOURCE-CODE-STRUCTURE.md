---
title: "Source Code Structure"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa source code structure cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Source traceability trọng yếu

| Chủ đề | Source |
|---|---|
| Frappe hooks/routing/scheduler | `voice_app/hooks.py` |
| Main API controller | `voice_app/api.py` |
| Meeting rename API | `voice_app/meeting_api.py` |
| Speaker matching | `voice_app/speaker_manager.py` |
| Task extraction | `voice_app/task_extractor.py` |
| Gemini STT | `voice_app/gemini_stt_client.py` |
| ElevenLabs STT | `voice_app/elevenlabs_client.py` |
| Audio conversion/chunking | `voice_app/audio_utils.py` |
| DOCX export | `voice_app/docx_utils.py` |
| Frontend API client | `frontend/src/api.js` |
| SPA root/screens | `frontend/src/App.vue`, `frontend/src/views/*.vue` |
| DocType schema | `voice_app/voice_app/doctype/*/*.json` |

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

