# 🏗️ TÀI LIỆU KIẾN TRÚC & SƠ ĐỒ ĐỐI TƯỢNG (OBJECT-TO-OBJECT FLOW): 2AS WORKSUITE (`voice_app`)

> **Dự án:** 2AS WorkSuite - AI Voice Transcription & Task Automation  
> **Ứng dụng:** `voice_app` (Frappe v15 App + Vue 3 SPA)  
> **Xem bản trực quan HTML (Có màu sắc & đồ họa):** Mở file [`SYSTEM_WORKFLOW.html`](file:///home/frappe/frappe-bench/apps/2as-worksuite/docs/SYSTEM_WORKFLOW.html)  

---

## 📑 MỤC LỤC
1. [Sơ đồ Luồng Đối tượng Trực quan (Unicode Box-Diagram)](#1-sơ-đồ-luồng-đối-tượng-trực-quan-unicode-box-diagram)
2. [Chi tiết Các Đối tượng Dữ liệu (Object Schemas)](#2-chi-tiết-các-đối-tượng-dữ-liệu-object-schemas)
3. [Quy trình Biến đổi Từng Bước (Step-by-Step Transformation)](#3-quy-trình-biến-đổi-từng-bước-step-by-step-transformation)
4. [Sơ đồ Nhận diện Giọng nói Sinh trắc học (Speaker Biometrics Flow)](#4-sơ-đồ-nhận-diện-giọng-nói-sinh-trắc-học-speaker-biometrics-flow)
5. [Sơ đồ Đồng bộ Tác vụ sang Worksuite ERP](#5-sơ-đồ-đồng-bộ-tác-vụ-sang-worksuite-erp)
6. [Cấu trúc Cơ sở Dữ liệu (DocType Schema)](#6-cấu-trúc-cơ-sở-dữ-liệu-doctype-schema)

---

## 1. Sơ đồ Luồng Đối tượng Trực quan (Unicode Box-Diagram)

```text
=====================================================================================================
                                 LUỒNG CHUYỂN HÓA ĐỐI TƯỢNG (OBJECT-TO-OBJECT)
=====================================================================================================

  [1. USER UPLOAD]
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 RawAudioFileObject                                       │
  │ • filename: "Hop_Trien_Khai_AI_2026.mp3" / .m4a / .wav      │
  │ • file_size: 45.2 MB | stream_buffer                        │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (ffmpeg / pydub normalization)
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 NormalizedWavObject                                      │
  │ • format: WAV PCM 16,000 Hz, 16-bit Mono                    │
  │ • total_duration: 3,420 giây (~57 phút)                     │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (WebRTC VAD: Cắt theo khoảng lặng câu nói)
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 AudioChunkObject [Chunk 1, Chunk 2, Chunk 3...]          │
  │ • chunk_id: "CHK-01", "CHK-02", "CHK-03"                   │
  │ • duration: ~10-15 phút / chunk                             │
  │ • bytes: audio chunk slices                                 │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (Gửi MapReduce song song + Nạp Global Vocabulary CT Group)
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 GeminiSTTResponseObject                                  │
  │ • raw_segments: [                                           │
  │     { start: "00:01:10", speaker: "Speaker 1", text: "..."} │
  │   ]                                                         │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (Trích xuất Vector 512 chiều & So khớp Cosine)
  ┌──────────────────────────────────────────────┐
  │ 👤 VoiceSpeakerProfile (DB Mẫu giọng)        │ ◄───► [scipy.spatial.distance.cosine]
  │ • "Anh Lê Thành - PAI" (Vector 512-dim)      │        (Độ tương đồng >= 0.75)
  └──────────────────────────────┬───────────────┘
                                 │
                                 ▼ (Gán danh tính thực vào từng câu thoại)
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 AnnotatedTranscriptSegment [1..M]                        │
  │ • speaker: "Anh Lê Thành (PAI)"                             │
  │ • time_range: "00:02:15 -> 00:03:40"                        │
  │ • content: "Nhóm AI sẽ hoàn thiện module STT trước 30/08."  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (Ghép nối toàn bộ hội thoại + Nạp Prompt Trích xuất)
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 FullMeetingTranscriptObject                              │
  │ • meeting_title: "Họp triển khai AI Voice App"              │
  │ • attendees: ["Anh Lê Thành", "Chị Mai Lan", "Chủ tịch"]    │
  │ • full_text: string                                         │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (OpenAI GPT-4o / Gemini Pro Reasoning)
  ┌─────────────────────────────────────────────────────────────┐
  │ 📦 LLMStructuredOutputObject (JSON)                         │
  │ ├── meeting_summary: "Tóm tắt kết luận & chỉ đạo cuộc họp"  │
  │ └── extracted_tasks: [                                      │
  │       {                                                     │
  │         task_title: "Hoàn thiện module STT",                │
  │         assignee: "Lê Thành Anh",                           │
  │         deadline: "2026-08-30",                             │
  │         priority: "High"                                    │
  │       }                                                     │
  │     ]                                                       │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼ (Tạo bản ghi dữ liệu Frappe DocTypes)
  ┌─────────────────────────────────────────────────────────────┐
  │ 🗄️ FRAPPE DATABASE ENTITIES                                 │
  │ ├── [DocType: Voice Meeting] (Lưu Transcript & Summary)     │
  │ ├── [DocType: Voice Meeting Chunk] (Lưu vết các Chunk)      │
  │ └── [DocType: Voice Task] (Lưu danh sách công việc bàn giao)│
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼ (Xuất Báo Cáo)                ▼ (Đồng bộ ERP)
  ┌──────────────────────────────┐ ┌──────────────────────────────┐
  │ 📄 WordReportFileObject      │ │ 🏢 WorksuiteTaskRecord (ERP) │
  │ • Định dạng: .docx           │ │ • POST /api/v1/tasks         │
  │ • Chuẩn biểu mẫu CT Group    │ │ • worksuite_task_id: 1849    │
  │ • Tự động tạo bảng Task      │ │ • Status: "Synced"           │
  └──────────────────────────────┘ └──────────────────────────────┘
```

---

## 2. Chi tiết Các Đối tượng Dữ liệu (Object Schemas)

### 🔹 1. Đối tượng Đoạn âm thanh (`AudioChunkObject`)
```json
{
  "chunk_id": "CHK_VOICE_001_01",
  "chunk_index": 1,
  "start_time_sec": 0.0,
  "end_time_sec": 624.5,
  "sample_rate": 16000,
  "audio_file_path": "/private/files/chunks/chunk_01.wav"
}
```

### 🔹 2. Đối tượng Đoạn thoại sau Định danh (`AnnotatedTranscriptSegment`)
```json
{
  "segment_index": 3,
  "start_time": "00:02:15",
  "end_time": "00:03:40",
  "raw_speaker_tag": "Speaker 2",
  "identified_speaker": {
    "speaker_id": "SPK-0012",
    "name": "Lê Thành Anh",
    "department": "PAI",
    "confidence_score": 0.89
  },
  "text": "Nhóm AI sẽ hoàn thiện module nhận diện giọng nói và bàn giao trước ngày 30 tháng 8."
}
```

### 🔹 3. Đối tượng Tác vụ & Tóm tắt AI (`LLMStructuredOutputObject`)
```json
{
  "meeting_summary": "Cuộc họp thống nhất tiến độ triển khai dự án AI Voice Transcription, phê duyệt kế hoạch tích hợp Worksuite ERP.",
  "key_decisions": [
    "Sử dụng Gemini Flash làm STT chính và GPT-4o cho bóc tách Task",
    "Đồng bộ trực tiếp Task sang Worksuite ERP sau khi họp xong"
  ],
  "tasks": [
    {
      "task_title": "Hoàn thiện module nhận diện giọng nói (Speaker Diarization)",
      "assignee": "Lê Thành Anh",
      "department": "PAI",
      "deadline": "2026-08-30",
      "priority": "High",
      "notes": "Trích xuất từ phát biểu của Lê Thành Anh lúc 00:02:15"
    }
  ]
}
```

---

## 3. Quy trình Biến đổi Từng Bước (Step-by-Step Transformation)

| Bước | Đối tượng Nguồn | Công cụ / Module xử lý | Đối tượng Đích | Ý nghĩa |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `RawAudioFileObject` | `ffmpeg` + `pydub` | `NormalizedWavObject` | Chuyển đổi định dạng audio bất kỳ về WAV chuẩn 16kHz Mono. |
| **2** | `NormalizedWavObject` | `webrtcvad` | `AudioChunkObject[]` | Cắt nhỏ audio thành các đoạn 10-15 phút tại đúng điểm im lặng. |
| **3** | `AudioChunkObject` | Google Gemini Flash STT | `GeminiSTTResponseObject` | Nhận diện giọng nói siêu tốc kèm nhãn Speaker tạm thời. |
| **4** | `GeminiSTTResponseObject` | `speaker_manager.py` (Cosine) | `AnnotatedTranscriptSegment[]` | So khớp vector âm học và gán đúng tên nhân sự phát biểu. |
| **5** | `FullMeetingTranscriptObject`| `task_extractor.py` (GPT-4o) | `LLMStructuredOutputObject` | Bóc tách đầu việc, người thực hiện, thời hạn và tóm tắt. |
| **6** | `LLMStructuredOutputObject` | Frappe ORM Controller | `DocType: Voice Meeting & Task`| Lưu trữ bền vững vào cơ sở dữ liệu hệ thống. |
| **7** | `DocType: Voice Task` | `api.py` (Worksuite Client) | `WorksuiteTaskRecord` | Đẩy task tự động vào phần mềm quản lý công việc của tập đoàn. |

---

## 4. Sơ đồ Nhận diện Giọng nói Sinh trắc học (Speaker Biometrics Flow)

```text
[Đoạn Audio ngắn (3-5s)] 
         │
         ▼ (Mô hình Pyannote / Resemblyzer)
[Vector giọng nói hiện tại: Float32Array[512]]
         │
         ▼ (Tính toán Cosine Distance với Thư viện Giọng mẫu)
 ┌────────────────────────────────────────────────────────┐
 │ So khớp với [DocType: Voice Speaker]:                  │
 │ • Mẫu 1: "Chủ tịch"       -> Cosine = 0.42 (Không khớp)│
 │ • Mẫu 2: "Anh Lê Thành"   -> Cosine = 0.91 (KHỚP!)     │
 │ • Mẫu 3: "Chị Mai Lan"    -> Cosine = 0.35 (Không khớp)│
 └────────────────────────┬───────────────────────────────┘
                          │
                          ▼
           [Gán nhãn: "Anh Lê Thành - PAI"]
```

---

## 5. Sơ đồ Đồng bộ Tác vụ sang Worksuite ERP

```text
[Bảng danh sách Voice Task trên Web] 
         │
         ▼ (Người dùng bấm nút "Đồng bộ sang Worksuite")
[Đọc URL & Sync Token từ "Voice App Settings"]
         │
         ▼ (Duyệt từng Task -> Map Assignee ID & Project ID)
[Gọi REST API: POST https://deverp.ctgroupvietnam.com/api/v1/tasks]
         │
         ▼
[Nhận Task ID từ ERP: vd #1849 -> Lưu vào Voice Task & set Status = "Synced"]
```

---

## 6. Cấu trúc Cơ sở Dữ liệu (DocType Schema)

| DocType | Kiểu | Trường dữ liệu chính | Quan hệ liên kết |
| :--- | :---: | :--- | :--- |
| **`Voice Meeting`** | Bảng chính | `name`, `title`, `meeting_date`, `audio_file`, `status`, `full_transcript`, `meeting_summary` | Cha của `Voice Task` và `Voice Meeting Chunk` (1:N) |
| **`Voice Meeting Chunk`** | Bảng phụ | `parent_meeting`, `chunk_index`, `start_time`, `end_time`, `chunk_transcript`, `status` | Thuộc về `Voice Meeting` |
| **`Voice Task`** | Bảng công việc | `parent_meeting`, `task_title`, `assignee`, `deadline`, `priority`, `status`, `worksuite_task_id` | Thuộc về `Voice Meeting` |
| **`Voice Speaker`** | Bảng nhân sự | `speaker_name`, `employee_code`, `department`, `voice_embedding_vector`, `sample_count` | Mẫu giọng học sinh trắc học |
| **`Voice App Settings`** | Singleton | `gemini_api_key`, `gemini_model`, `gemini_stt_max_output_tokens`, `openai_api_key`, `worksuite_url`, `global_vocabulary` | Cấu hình toàn app |

---

> 💡 **Mẹo:** Bạn có thể mở file [`SYSTEM_WORKFLOW.html`](file:///home/frappe/frappe-bench/apps/2as-worksuite/docs/SYSTEM_WORKFLOW.html) bằng trình duyệt web để xem giao diện đồ họa trực quan, có màu sắc khối hộp và hiệu ứng đầy đủ!
