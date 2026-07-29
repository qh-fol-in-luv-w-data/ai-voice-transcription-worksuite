---
title: "Screen Inventory"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa screen inventory cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

| Screen ID | Screen | Route/State | Module | Purpose | API used | States | Permission | Source |
|---|---|---|---|---|---|---|---|---|
| SCR-001 | Phân tích Hội thoại | `activeTab='transcribe'` | Transcription | Upload/review/extract | `transcribeAudio`, `checkMeetingStatus`, `extractTasks` | loading/progress/error | Auth | `VoiceTranscribe.vue` |
| SCR-002 | Tự tạo Task qua Voice | `activeTab='voice_task'` | Voice Task | STT câu lệnh task | `voiceToTask`, `syncTasksToERP` | recording/loading/error | Auth | `VoiceTask.vue` |
| SCR-003 | Đăng ký Giọng nói | `activeTab='enroll'` | Speaker | Enroll voice sample | `enrollVoice` | recording/uploading/error | Auth | `VoiceEnroll.vue` |
| SCR-004 | Lịch sử Cuộc họp | Modal/sidebar + `view_meeting` | Meeting | Open/rename past meeting | `getMeetingHistory`, `renameMeeting` | empty/list/edit | Owner | `AppSidebar.vue`, `MeetingHistory.vue` |
| SCR-005 | Task Modal | Global modal | Task | Review/edit/export/sync tasks | `saveMeetingDraft`, `exportDynamicDocx`, `syncTasksToERP` | open/closed/error | Auth | `TaskModal.vue` |

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

