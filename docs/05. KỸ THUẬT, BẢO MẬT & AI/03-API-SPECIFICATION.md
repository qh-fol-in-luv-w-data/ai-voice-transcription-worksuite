---
title: "API Specification"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa api specification cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| API ID | Method | Path | Description | Auth | Params/body | Response | Source |
|---|---|---|---|---|---|---|---|
| API-001 | POST | `/api/method/voice_app.api.transcribe_audio` | Upload audio and enqueue STT | Session | FormData file, language, stt_mode, num_speakers, custom_vocabulary | `{status, meeting_name}` | `api.py` |
| API-002 | GET | `/api/method/voice_app.api.check_meeting_status` | Poll meeting status/result | Session | meeting_name | processing/success/error | `api.py` |
| API-003 | POST | `/api/method/voice_app.api.extract_tasks` | Enqueue task extraction | Session | results, meeting_name, model_type, meeting metadata | `{status:'processing'}` | `api.py` |
| API-004 | GET | `/api/method/voice_app.api.check_extract_status` | Poll task extraction | Session | meeting_name | processing/success/error | `api.py` |
| API-005 | GET | `/api/method/voice_app.api.get_employees` | Fetch active employees | Session | none | employees | `api.py` |
| API-006 | POST | `/api/method/voice_app.api.sync_tasks_to_erp` | Sync tasks | Session | tasks[] | success/report or error | `api.py` |
| API-007 | GET | `/api/method/voice_app.api.get_elevenlabs_info` | Balance info | Session | none | balance | `api.py` |
| API-008 | POST | `/api/method/voice_app.api.enroll_voice` | Enroll current user voice | Session | file | status/message | `api.py` |
| API-009 | GET | `/api/method/voice_app.api.get_enrolled_speakers` | List speakers | Session | none | speakers | `api.py` |
| API-010 | POST | `/api/method/voice_app.api.update_meeting_results` | Save edited segments | Session | meeting_name, results | status | `api.py` |
| API-011 | POST | `/api/method/voice_app.api.map_and_enroll_speakers` | Map speaker labels and enroll | Session | meeting_name, mappings | status | `api.py` |
| API-012 | POST | `/api/method/voice_app.api.voice_to_task` | Create/refine task from voice | Session | file, existing_task, job_key | task JSON | `api.py` |
| API-013 | POST | `/api/method/voice_app.api.resume_transcription` | Resume failed/partial meeting | Session | meeting_name | status | `api.py` |
| API-014 | POST | `/api/method/voice_app.api.undo_mapping` | Restore original speaker mapping | Session | meeting_name | status | `api.py` |
| API-015 | GET/POST | `/api/method/voice_app.api.get_global_vocabulary` / `save_global_vocabulary` | Read/write vocabulary | Session | vocabulary | status/message | `api.py` |
| API-016 | POST | `/api/method/voice_app.api.export_dynamic_docx` | Export DOCX from saved draft | Session | meeting_name | file url | `api.py` |
| API-017 | POST | `/api/method/voice_app.api.save_meeting_draft` | Save summary/conclusion/tasks draft | Session | meeting_name, summary, conclusion, tasks_json_str | status | `api.py` |
| API-018 | POST | `/api/method/voice_app.api.proctoring_webhook` | Inbound proctoring alert | Guest allowed + optional secret | JSON session_id, alert_type | event/summary | `api.py` |
| API-019 | POST | `/api/method/voice_app.meeting_api.rename_meeting` | Rename meeting | Session | meeting_name, new_title | status | `meeting_api.py` |

Rate limit: NOT FOUND custom rate limiting. Status codes mostly Frappe defaults plus explicit 400/401 in proctoring webhook.

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

