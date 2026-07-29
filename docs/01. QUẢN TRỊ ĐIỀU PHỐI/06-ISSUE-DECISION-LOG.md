---
title: "Issue Decision Log"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa issue decision log cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Issue log

| ID | Issue | Impact | Owner | Status |
|---|---|---|---|---|
| ISS-01 | `scheduler_events` gọi `voice_app.api.cleanup_old_chunks` nhưng chưa thấy function trong `api.py`. | Daily job có thể lỗi. | Backend | Open |

### Decision log

| ID | Decision | Rationale | Source | Status |
|---|---|---|---|---|
| ADR-LINK-01 | Chạy AI/audio nặng qua queue/subprocess. | Tránh block request và lỗi PyTorch fork. | `voice_app/api.py`, `voice_app/speaker_manager.py` | Accepted |

### Assumption log

| ID | Assumption | Validation |
|---|---|---|
| ASM-01 | Production chạy trên Frappe Bench/Frappe Cloud hoặc server tương đương. | TODO |

### Dependency log

| ID | Dependency | Owner | Risk |
|---|---|---|---|
| DEP-01 | OpenAI/Gemini/ElevenLabs/HuggingFace/Worksuite | DevOps/Product | API key/quota/network |

### Change request log

| CR | Request | Impact | Status |
|---|---|---|---|
| CR-01 | TODO: Cần xác nhận quy trình change control chính thức. | Governance | Draft |

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

