---
title: "Documentation README"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Giới thiệu bộ tài liệu dự án và cách điều hướng.

## Phạm Vi

Áp dụng cho toàn bộ tài liệu trong `docs/`.

## Đối Tượng Sử Dụng

Tất cả thành viên dự án và bên nghiệm thu.

## Nội Dung Chi Tiết

### Project overview

`2AS WorkSuite - AI Voice Transcription & Task Automation` là ứng dụng Frappe + Vue giúp xử lý âm thanh cuộc họp, nhận diện người nói, xuất biên bản và tạo task đồng bộ Worksuite.

### Directory navigation

| Thư mục | Nội dung |
|---|---|
| `01. QUẢN TRỊ ĐIỀU PHỐI` | Charter, scope, risk, issue, communication. |
| `02. NGHIỆP VỤ & YÊU CẦU` | Process, actor, requirement, use case, traceability. |
| `03. UI-UX & TRẢI NGHIỆM` | Screen inventory, flows, design system, accessibility. |
| `04. KIẾN TRÚC, DỮ LIỆU & PHÂN TÍCH` | Architecture, module, database, data flow, ADR. |
| `05. KỸ THUẬT, BẢO MẬT & AI` | Developer guide, API spec, auth, security, AI docs. |
| `06. KIỂM THỬ & NGHIỆM THU` | Strategy, test cases, UAT, acceptance. |
| `07. RELEASE, DEVOP & GO-LIVE` | Deploy, release, go-live, rollback, DR. |
| `08. VẬN HÀNH, HỖ TRỢ & ĐO GIÁ TRỊ` | Operations, runbook, monitoring, support, KPI. |

### How to update

- Khi API thay đổi, cập nhật `05. KỸ THUẬT, BẢO MẬT & AI/03-API-SPECIFICATION.md` và traceability.
- Khi DocType thay đổi, cập nhật `04. KIẾN TRÚC, DỮ LIỆU & PHÂN TÍCH/03-DATABASE-DESIGN.md`.
- Khi workflow hoặc UI thay đổi, cập nhật nhóm `02` và `03`.
- Không ghi secret thật vào tài liệu.

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

