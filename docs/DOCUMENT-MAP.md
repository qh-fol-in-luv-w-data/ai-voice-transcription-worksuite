---
title: "Document Map"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Bản đồ liên kết requirement, UI, API, database, source, test, deployment và operations.

## Phạm Vi

Toàn bộ bộ tài liệu dự án.

## Đối Tượng Sử Dụng

PM, BA, QA, auditor, developer.

## Nội Dung Chi Tiết

| Business requirement | UI | API | Database | Source | Test | Deployment | Operations |
|---|---|---|---|---|---|---|---|
| FR-001 Transcribe | SCR-001 | API-001/API-002 | Voice Meeting/Chunk | `voice_app/api.py` | TC-001..003 | Deployment Guide | Runbook queue/STT |
| FR-003 Speaker enroll | SCR-003 | API-008/API-009 | Voice Speaker | `speaker_manager.py` | TC-004 | Config Guide | Troubleshooting speaker |
| FR-006 Extract tasks | SCR-005 | API-003/API-004 | Voice Meeting | `task_extractor.py` | TC-006/007 | Go-live Checklist | Provider monitoring |
| FR-007 ERP sync | SCR-005 | API-006 | External Task | `create_tasks_to_erp()` | TC-008 | Environment Matrix | ERP runbook |
| AUTH Owner access | All | API auth checks | Frappe owner fields | `_can_access_meeting()` | TC-009 | Security Checklist | Incident Management |

## Giả Định

- ASSUMPTION: Dự án được triển khai như một Frappe app trong Frappe Bench v15+ theo README hiện tại.
- ASSUMPTION: Các URL môi trường ngoài local cần được đội vận hành xác nhận.

## Vấn Đề Cần Xác Nhận

- TODO: Cần xác nhận owner tài liệu, người phê duyệt, SLA/SLO, RTO/RPO và môi trường production chính thức.
- NOT FOUND: Không tìm thấy CI/CD workflow, Dockerfile, Kubernetes manifest hoặc `.env.example` trong workspace hiện tại.


## Tài Liệu Liên Quan

- [README](README.md)
- [Document Map](DOCUMENT-MAP.md)
- [Project Discovery](00-PROJECT-DISCOVERY.md)

## Lịch Sử Thay Đổi

| Ngày | Phiên bản | Thay đổi | Tác giả |
|---|---:|---|---|
| 2026-07-28 | 0.1 | AI bổ sung tài liệu ban đầu từ source code. | Codex |

