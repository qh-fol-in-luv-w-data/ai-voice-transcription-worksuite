---
title: "User Stories"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa user stories cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Story ID | As a | I want | So that | Acceptance | Related API | Screen |
|---|---|---|---|---|---|---|
| US-001 | User | upload meeting audio | có transcript nhanh | Meeting completes with transcript | `transcribe_audio` | `VoiceTranscribe.vue` |
| US-002 | User | chỉnh tên speaker sai | biên bản đúng người nói | Segment labels updated | `reassign_speaker_from_segment` | `VoiceTranscribe.vue`, `MeetingHistory.vue` |
| US-003 | User | đăng ký giọng nói | lần sau hệ thống nhận diện tự động | Speaker saved | `enroll_voice` | `VoiceEnroll.vue` |
| US-004 | User | tạo task từ biên bản | không bỏ sót action item | TaskModal shows tasks | `extract_tasks` | `TaskModal.vue` |
| US-005 | User | đồng bộ task ERP | triển khai công việc trong Worksuite | ERP sync success | `sync_tasks_to_erp` | `TaskModal.vue` |

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

