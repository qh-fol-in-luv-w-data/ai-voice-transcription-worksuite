---
title: "Glossary"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Chuẩn hóa thuật ngữ nghiệp vụ/kỹ thuật.

## Phạm Vi

Các thuật ngữ xuất hiện trong app và tài liệu.

## Đối Tượng Sử Dụng

Tất cả thành viên dự án.

## Nội Dung Chi Tiết

| Term | Meaning |
|---|---|
| STT | Speech-to-Text, chuyển âm thanh thành văn bản. |
| Diarization | Phân tách người nói theo thời gian. |
| Voice Meeting | DocType lưu cuộc họp và kết quả phân tích. |
| Voice Meeting Chunk | DocType lưu chunk audio và kết quả STT từng phần. |
| Voice Speaker | DocType lưu người đã đăng ký giọng và embedding. |
| VOICE Session | Session audit/log usage của app. |
| raw_results | JSON segment gồm speaker/time/text. |
| tasks_json | JSON task/noti trích xuất từ cuộc họp. |
| Worksuite/CTERP | Hệ thống ERP bên ngoài để lấy Employee/Project và sync Task. |
| `Pending/Processing/Completed/Error/Analyzed/Synced` | Status của `Voice Meeting`. |
| `Partial Error` | Status runtime có trong code nhưng chưa có trong DocType options; cần xác nhận. |

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

