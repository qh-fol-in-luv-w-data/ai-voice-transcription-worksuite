---
title: "Solution Architecture"
project: "2AS WorkSuite - AI Voice Transcription & Task Automation"
version: "0.1"
status: "Draft"
owner: "TODO"
last_updated: "2026-07-28"
source_of_truth: "Source code and project configuration"
---

## Mục Đích

Tài liệu hóa solution architecture cho dự án dựa trên source code hiện tại.

## Phạm Vi

Phạm vi bám theo app `voice_app`, frontend `frontend/src`, DocType schema và các tích hợp trong source.

## Đối Tượng Sử Dụng

Các vai trò dự án liên quan: PM/BA/Dev/QA/DevOps/Security/Ops.

## Nội Dung Chi Tiết

### Architecture overview

```mermaid
flowchart LR
  U[Browser SPA Vue] -->|Frappe session + CSRF| F[Frappe voice_app API]
  F --> DB[(Frappe MariaDB DocTypes)]
  F --> R[(Redis cache/realtime/queue)]
  F --> FILES[(Frappe File storage)]
  F --> G[Google Gemini STT]
  F --> EL[ElevenLabs STT]
  F --> OA[OpenAI GPT]
  F --> HF[HuggingFace/Pyannote embedding]
  F --> WS[Worksuite/CTERP APIs]
```

```mermaid
flowchart TD
  C1[Container: Vue SPA] --> C2[Container: Frappe Python App]
  C2 --> C3[Queue Worker long]
  C3 --> C4[AI/STT Providers]
  C2 --> C5[MariaDB DocTypes]
  C2 --> C6[Redis Cache/Realtime]
```

### Design decisions

- Async long tasks via `frappe.enqueue`.
- Realtime progress via `frappe.publish_realtime`.
- Speaker embedding normalization before save/match.
- Secrets loaded from `Voice App Settings`, `site_config` or env, never frontend.

Known limitations: no CI/CD found; dependency/provider failures need operational monitoring.

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

