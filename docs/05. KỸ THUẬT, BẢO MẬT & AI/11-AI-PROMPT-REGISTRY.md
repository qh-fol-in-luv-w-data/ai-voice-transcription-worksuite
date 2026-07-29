---
title: "AI Prompt Registry"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa ai prompt registry cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Prompt ID | Use case | Input variables | Output format | Guardrail | Source |
|---|---|---|---|---|---|
| PR-001 | Extract tasks from DOCX | `doc_text`, model_type | JSON object with `ten_cuoc_hop`, `items`, summary/conclusion | No markdown, response_format JSON | `task_extractor.py` — `node_extract_tasks()` |
| PR-002 | Voice-to-task parse/refine | `full_text`, `existing_task`, projects, employees, current date/user | JSON object with task_name/project/assignee/dates/missing_fields | No markdown, response_format JSON, clarification question | `api.py` — `_voice_to_task_async()` |
| PR-003 | Speaker name mapping via LLM | `segments`, `speaker_names` | JSON mapping | TODO: inspect prompt before approval | `task_extractor.py` — `map_speakers_llm()` |
| PR-004 | Gemini STT prompt | language, num_speakers, vocabulary | STT JSON/segments | parse/clean response | `gemini_stt_client.py` — `_build_prompt()` |

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

