# 🏗️ TÀI LIỆU KIẾN TRÚC & TOÀN BỘ LUỒNG HOẠT ĐỘNG: 2AS WORKSUITE (`voice_app`)

> **Dự án:** 2AS WorkSuite - AI Voice Transcription & Task Automation  
> **Phiên bản:** 2.0  
> **Ứng dụng:** `voice_app` (Frappe v15 App + Vue 3 SPA)  
> **Tác giả:** Đội ngũ AI Engineering - CT Group  

---

## 📑 MỤC LỤC
1. [Tổng quan Kiến trúc Hệ thống (System Architecture)](#1-tổng-quan-kiến-trúc-hệ-thống-system-architecture)
2. [Sơ đồ Luồng Xử lý Toàn trình (End-to-End Sequence Diagram)](#2-sơ-đồ-luồng-xử-lý-toàn-trình-end-to-end-sequence-diagram)
3. [Luồng Xử lý Âm thanh & MapReduce Chunking](#3-luồng-xử-lý-âm-thanh--mapreduce-chunking)
4. [Luồng Nhận diện Giọng nói Sinh trắc học (Speaker Biometrics & Diarization)](#4-luồng-nhận-diện-giọng-nói-sinh-trắc-học-speaker-biometrics--diarization)
5. [Luồng Bóc tách Tác vụ AI & Tạo Biên bản Họp (Task Extraction & Minutes)](#5-luồng-bóc-tách-tác-vụ-ai--tạo-biên-bản-họp-task-extraction--minutes)
6. [Luồng Đồng bộ Hóa Tác vụ sang Worksuite ERP](#6-luồng-đồng-bộ-hóa-tác-vụ-sang-worksuite-erp)
7. [Cấu trúc Cơ sở Dữ liệu & Thực thể (DocType Schema ERD)](#7-cấu-trúc-cơ-sở-dữ-liệu--thực-thể-doctype-schema-erd)
8. [Danh mục API & Module Mapping](#8-danh-mục-api--module-mapping)

---

## 1. Tổng quan Kiến trúc Hệ thống (System Architecture)

```mermaid
graph TB
    subgraph Client["📱 1. Client Layer (Vue 3 + Vite SPA)"]
        UI["Vue 3 Frontend (/aicenter/voice_app)"]
        Recorder["Trình ghi âm trực tiếp / Upload Audio File"]
        Editor["Trình hiệu chỉnh Transcript & Phân vai Speaker"]
        TaskGrid["Bảng Kanban & Danh sách Action Items"]
        WSClient["Socket.io / Realtime Client"]
    end

    subgraph FrappeCore["⚙️ 2. Frappe Application Core (voice_app)"]
        Router["Frappe Whitelist API Controller (voice_app.api)"]
        AudioProcessor["Audio Preprocessor & VAD (pydub, ffmpeg, webrtcvad)"]
        Chunker["MapReduce Audio Chunker (Voice Meeting Chunk)"]
        STTOrchestrator["STT Orchestrator (gemini_stt_client / whisper)"]
        SpeakerMatcher["Voice Biometrics Matcher (speaker_manager.py)"]
        TaskExtractor["AI Task & Summary Extractor (task_extractor.py)"]
        DocxGen["Corporate DOCX Generator (docx_utils.py)"]
        WorksuiteSync["Worksuite Sync Engine (REST Client)"]
        RealtimePub["Frappe Realtime Event Publisher"]
    end

    subgraph AICloud["🧠 3. AI Cloud Services & Engines"]
        GeminiSTT["Google Gemini Multimodal STT (gemini-1.5/2.0-flash)"]
        WhisperSTT["OpenAI Whisper / ElevenLabs Scribe"]
        OpenAILLM["OpenAI GPT-4o / Gemini Pro (LLM Reasoning)"]
        EmbeddingAPI["Voice Embedding Model (Pyannote / Resemblyzer)"]
    end

    subgraph Database["💾 4. Persistence Layer (Frappe PostgreSQL/MariaDB)"]
        DocMeeting[("DocType: Voice Meeting")]
        DocChunk[("DocType: Voice Meeting Chunk")]
        DocTask[("DocType: Voice Task")]
        DocSpeaker[("DocType: Voice Speaker (Vectors)")]
        DocSettings[("DocType: Voice App Settings")]
        DocLogs[("DocType: Action & AI Call Logs")]
    end

    subgraph External["🏢 5. Enterprise Integration"]
        WorksuiteERP["Worksuite ERP / Project Management System"]
    end

    %% Client Interactions
    Recorder -->|1. Upload Audio/Video File| Router
    Router --> AudioProcessor
    WSClient <-->|Realtime Progress Events| RealtimePub

    %% Core Pipeline
    AudioProcessor --> Chunker
    Chunker --> STTOrchestrator
    STTOrchestrator --> GeminiSTT
    STTOrchestrator --> WhisperSTT
    STTOrchestrator --> SpeakerMatcher
    SpeakerMatcher <--> EmbeddingAPI
    SpeakerMatcher <--> DocSpeaker

    STTOrchestrator --> TaskExtractor
    TaskExtractor --> OpenAILLM
    TaskExtractor --> DocMeeting
    TaskExtractor --> DocTask
    Chunker --> DocChunk

    Editor -->|2. Hiệu chỉnh dữ liệu thoại| Router
    TaskGrid -->|3. Yêu cầu xuất DOCX / Đồng bộ| Router
    Router --> DocxGen
    Router --> WorksuiteSync
    WorksuiteSync -->|4. Push Tasks qua REST API| WorksuiteERP
    DocSettings -.->|Cấu hình Keys & Token Caps| Router
```

---

## 2. Sơ đồ Luồng Xử lý Toàn trình (End-to-End Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    actor User as 👤 Người dùng (Frontend)
    participant API as 🚀 Frappe API (voice_app.api)
    participant Audio as 🎵 Audio Preprocessor
    participant STT as 🎙️ Gemini STT & Diarization
    participant Bio as 🧬 Speaker Manager
    participant LLM as 🧠 NLP Task Extractor
    participant DB as 🗄️ Database (DocTypes)
    participant ERP as 🏢 Worksuite ERP

    %% Phase 1: Upload & Preprocess
    Note over User, Audio: Giai đoạn 1: Tiếp nhận và Tiền xử lý âm thanh
    User->>API: Upload file ghi âm cuộc họp (.mp3, .wav, .m4a, .mp4)
    API->>DB: Tạo bản ghi Voice Meeting (Trạng thái: "Processing")
    API->>Audio: Chuẩn hóa 16kHz Mono WAV, đo thời lượng & lọc nhiễu
    Audio->>Audio: Cắt đoạn MapReduce theo quãng lặng VAD (Chunks ~10-15 phút)
    Audio->>DB: Lưu các bản ghi Voice Meeting Chunk

    %% Phase 2: STT & Diarization
    Note over API, Bio: Giai đoạn 2: Phiên âm STT & Nhận diện Giọng nói
    loop Xử lý song song từng Chunk
        API->>STT: Gửi Audio Chunk + Vocabulary vào Gemini STT
        STT-->>API: Trả về Sub-Transcript kèm Timestamps & Speaker ID (Speaker 1, 2,...)
        API->>Bio: Trích xuất Voice Embedding đặc trưng từ Audio Segment
        Bio->>DB: So khớp Cosine Similarity với Vector giọng mẫu trong Voice Speaker
        Bio-->>API: Gán danh tính thực (vd: "Anh Lê Thành - PAI")
        API-->>User: [WebSocket] Bắn sự kiện cập nhật tiến độ Realtime (%)
    end

    %% Phase 3: Task Extraction & Summary
    Note over API, LLM: Giai đoạn 3: Phân tích Văn bản & Trích xuất Tác vụ
    API->>LLM: Ghép nối toàn bộ Transcript + Gửi Prompt bóc tách Task & Tóm tắt
    LLM-->>API: Trả về JSON: Tóm tắt cuộc họp, Action Items, Deadline, Người phụ trách
    API->>DB: Cập nhật Voice Meeting & Tự động tạo các bản ghi Voice Task
    API-->>User: Trả về kết quả hoàn chỉnh hiển thị lên giao diện Web

    %% Phase 4: Verification & Export
    Note over User, ERP: Giai đoạn 4: Hiệu chỉnh, Xuất Biên bản & Đồng bộ ERP
    opt Người dùng chỉnh sửa & Xuất Word
        User->>API: Chỉnh sửa Text / Speaker / Deadline trên giao diện
        API->>DB: Cập nhật lại Voice Meeting & Voice Task
        User->>API: Bấm nút "Xuất Biên bản họp (.docx)"
        API-->>User: Tải về file Word định dạng chuẩn Tập đoàn CT Group
    end

    opt Đồng bộ Task sang Worksuite ERP
        User->>API: Bấm nút "Đồng bộ sang Worksuite"
        API->>DB: Lấy danh sách Voice Task & Thông tin xác thực trong Voice App Settings
        API->>ERP: Gọi REST API tạo Task / Milestone trên Worksuite ERP
        ERP-->>API: Trả về Worksuite Task ID
        API->>DB: Cập nhật trạng thái Voice Task sang "Synced"
        API-->>User: Thông báo đồng bộ thành công
    end
```

---

## 3. Luồng Xử lý Âm thanh & MapReduce Chunking

```mermaid
flowchart TD
    Start([Bắt đầu: File Audio/Video Input]) --> CheckExt{Kiểm tra định dạng file}
    CheckExt -->|MP3, M4A, MP4, AAC, OGG| FFMPEG[Chuyển đổi sang WAV 16kHz Mono qua ffmpeg]
    CheckExt -->|WAV| CheckLength[Kiểm tra thời lượng audio]
    FFMPEG --> CheckLength

    CheckLength --> DurationCheck{Thời lượng > 15 phút<br/>hoặc dung lượng > 20MB?}
    
    DurationCheck -->|Không| SingleChunk[Xử lý trực tiếp toàn bộ file]
    DurationCheck -->|Có: Áp dụng MapReduce| VADSplit[Dò tìm các khoảng lặng giọng nói - WebRTC VAD]
    
    VADSplit --> SplitPoints[Xác định điểm cắt tối ưu tại ranh giới câu nói]
    SplitPoints --> ChunkCreate[Sinh ra N file Audio Chunks nhỏ ~10 phút]
    
    ChunkCreate --> ParallelSTT[Xử lý song song STT đa luồng qua Gemini]
    SingleChunk --> ParallelSTT

    ParallelSTT --> MergeChunks[Hợp nhất Transcript & Căn chỉnh Timestamps liên tục]
    MergeChunks --> EndAudio([Hoàn tất: Full Diarized Transcript])
```

---

## 4. Luồng Nhận diện Giọng nói Sinh trắc học (Speaker Biometrics & Diarization)

```mermaid
flowchart LR
    SegAudio[Đoạn âm thanh chứa giọng nói của Speaker X] --> Extractor[Voice Embedding Model<br/>Trích xuất Vector 512 chiều]
    Extractor --> Vector[(Vector Giọng nói Hiện tại)]
    
    Vector --> DBQuery[(Thư viện Voice Speaker DB<br/>Chứa mẫu giọng nhân sự đã học)]
    
    DBQuery --> CosineCalc[Tính khoảng cách Cosine Similarity<br/>scipy.spatial.distance.cosine]
    
    CosineCalc --> MatchCheck{Độ tương đồng >= 0.75?}
    
    MatchCheck -->|Có| AssignName[Gán tên nhân sự đã nhận diện<br/>vd: 'Anh Lê Thành - PAI']
    MatchCheck -->|Không| Fallback[Giữ nguyên nhãn tạm<br/>'Speaker 1 / Người nói 1']
    
    AssignName --> UpdateTranscript[Cập nhật vào dòng thoại Transcript]
    Fallback --> UpdateTranscript
```

---

## 5. Luồng Bóc tách Tác vụ AI & Tạo Biên bản Họp (Task Extraction & Minutes)

```mermaid
flowchart TD
    FullText[Full Diarized Transcript] --> PromptBuilder[Ghép System Prompt chuyên dụng + Context]
    
    PromptBuilder --> LLMEngine[OpenAI GPT-4o / Gemini Pro Reasoning]
    
    LLMEngine --> JSONOutput{Phân tích cấu trúc JSON}
    
    JSONOutput --> SummarySection[1. Tóm tắt Nội dung Cuộc họp & Ý kiến Lãnh đạo]
    JSONOutput --> TaskSection[2. Ma trận Công việc: Task, Assignee, Deadline, Priority]
    JSONOutput --> DecisionSection[3. Kết luận & Quyết định chính]
    
    SummarySection --> SaveDB[Lưu vào DocType Voice Meeting]
    TaskSection --> SaveTasks[Tạo các bản ghi DocType Voice Task]
    DecisionSection --> SaveDB
    
    SaveDB & SaveTasks --> ExportDocx[Nạp dữ liệu vào Template docx_utils.py]
    ExportDocx --> FileDownload([File Biên bản họp .docx chuẩn CT Group])
```

---

## 6. Luồng Đồng bộ Hóa Tác vụ sang Worksuite ERP

```mermaid
flowchart TD
    UserTrigger([Người dùng bấm 'Đồng bộ sang Worksuite']) --> GetTasks[Lấy danh sách Voice Task đang ở trạng thái 'Pending']
    GetTasks --> GetSettings[Đọc Worksuite URL & API Token từ 'Voice App Settings']
    
    GetSettings --> LoopTasks{Duyệt từng Task}
    
    LoopTasks --> ProjectMap[Ánh xạ Tên Dự án & Nhân sự trên Worksuite]
    ProjectMap --> APICall[Gọi REST API: POST /api/v1/tasks]
    
    APICall --> ResCheck{Kết quả gọi API?}
    
    ResCheck -->|Thành công| UpdateTask[Lưu worksuite_task_id & set status = 'Synced']
    ResCheck -->|Thất bại| LogError[Ghi nhật ký Voice AI Call Log & gắn cờ lỗi]
    
    UpdateTask --> NextCheck{Còn Task tiếp theo?}
    LogError --> NextCheck
    
    NextCheck -->|Còn| LoopTasks
    NextCheck -->|Hết| FinishSync([Hoàn tất: Báo cáo kết quả đồng bộ])
```

---

## 7. Cấu trúc Cơ sở Dữ liệu & Thực thể (DocType Schema ERD)

```mermaid
erDiagram
    Voice_Meeting ||--o{ Voice_Meeting_Chunk : "chứa các chunk"
    Voice_Meeting ||--o{ Voice_Task : "chứa các task"
    Voice_Speaker ||--o{ Voice_Meeting : "tham gia vào"
    Voice_App_Settings ||--|| Voice_Meeting : "cấu hình chung"
    Voice_Meeting ||--o{ Voice_AI_Call_Log : "lưu vết AI call"

    Voice_Meeting {
        string name PK "Mã cuộc họp (VOICE-MEET-YYYY-XXXXX)"
        string title "Tiêu đề cuộc họp"
        datetime meeting_date "Thời gian họp"
        string audio_file "Đường dẫn file ghi âm gốc"
        string status "Uploaded | Processing | Completed | Failed"
        longtext full_transcript "Toàn bộ nội dung hội thoại"
        longtext meeting_summary "Tóm tắt & kết luận cuộc họp"
        string created_by "Người khởi tạo"
    }

    Voice_Meeting_Chunk {
        string name PK "Mã chunk"
        string parent_meeting FK "Liên kết Voice Meeting"
        int chunk_index "Thứ tự chunk"
        float start_time "Thời điểm bắt đầu (giây)"
        float end_time "Thời điểm kết thúc (giây)"
        text chunk_transcript "Văn bản thoại đoạn này"
        string status "Done | Failed"
    }

    Voice_Task {
        string name PK "Mã task (VOICE-TASK-XXXXX)"
        string parent_meeting FK "Cuộc họp gốc"
        string task_title "Nội dung đầu việc"
        string assignee "Người chịu trách nhiệm"
        date deadline "Hạn hoàn thành"
        string priority "High | Medium | Low"
        string status "Pending | Synced | Cancelled"
        string worksuite_task_id "ID tác vụ tương ứng trên ERP"
    }

    Voice_Speaker {
        string name PK "Tên định danh người nói"
        string speaker_name "Họ và tên đầy đủ"
        string employee_code "Mã nhân viên"
        string department "Phòng ban / Đơn vị"
        blob voice_embedding_vector "Vector sinh trắc học giọng nói"
        int sample_count "Số lượng mẫu giọng đã học"
    }

    Voice_App_Settings {
        string whisper_url "URL Whisper local/server"
        string gemini_api_key "API Key Google Gemini"
        string gemini_model "Tên model Gemini STT"
        int gemini_stt_max_output_tokens "Trần token tối đa của STT"
        string openai_api_key "API Key OpenAI"
        string worksuite_url "Địa chỉ Worksuite ERP"
        string sync_api_token "Token xác thực Worksuite"
        text global_vocabulary "Từ điển thuật ngữ doanh nghiệp CT Group"
    }

    Voice_AI_Call_Log {
        string name PK
        string meeting_id FK
        string provider "Google Gemini | OpenAI | ElevenLabs"
        int prompt_tokens
        int completion_tokens
        float latency_ms
        string status "Success | Error"
    }
```

---

## 8. Danh mục API & Module Mapping

| Endpoint API (Frappe Method) | Module nguồn | Mục đích sử dụng |
| :--- | :--- | :--- |
| `voice_app.api.get_context` | `voice_app/api.py` | Khởi tạo phiên làm việc, cấp CSRF token và thông tin user hiện tại. |
| `voice_app.api.process_meeting_audio` | `voice_app/api.py` | Tiếp nhận file audio, kích hoạt toàn bộ pipeline MapReduce STT. |
| `voice_app.api.get_meeting_detail` | `voice_app/api.py` | Lấy chi tiết Transcript, danh sách Speaker, Tóm tắt và Task của cuộc họp. |
| `voice_app.api.update_transcript_segment`| `voice_app/api.py` | Cập nhật đoạn văn bản thoại hoặc gán lại Speaker thủ công. |
| `voice_app.api.extract_tasks` | `voice_app/task_extractor.py`| Chạy lại AI LLM để bóc tách lại Task và Action Items từ Transcript. |
| `voice_app.api.export_docx` | `voice_app/docx_utils.py` | Xuất Biên bản cuộc họp chính thức ra định dạng `.docx` theo chuẩn CT Group. |
| `voice_app.api.sync_to_worksuite` | `voice_app/api.py` | Đẩy danh sách Voice Task đã duyệt sang hệ thống Worksuite ERP. |
| `voice_app.api.register_speaker_sample` | `voice_app/speaker_manager.py` | Nạp mẫu âm thanh mới để huấn luyện nhận diện giọng nói cho nhân sự. |

---

## 💡 9. Tổng kết Giá trị Nghiệp vụ:
- **Tự động hóa 100% quy trình họp:** Từ lúc bật ghi âm đến khi sinh ra Biên bản họp hoàn chỉnh chỉ mất **1-2 phút**.
- **Chính xác theo văn hóa CT Group:** Nhận diện chuẩn xác các từ khóa đặc thù như *CT Group, CCTPA, VGCT, Metrostar, Green Bond, Carbon Credit, LiDAR, eVTOL...*
- **Liên thông dữ liệu:** Không còn tình trạng giao việc miệng bị quên; mọi cam kết trong cuộc họp đều được chuyển thành Task số trên hệ thống ERP ngay lập tức.
