# 📋 BÁO CÁO PHÂN TÍCH HỆ THỐNG 2AS-WORKSUITE

> **Ngày phân tích:** 11/07/2026  
> **Source path:** `d:\CTGroup\Mlops\data_center\ct_agent_hub_BE\frappe-bench\apps\2as-worksuite`  
> **Platform:** Frappe Framework (Python Backend + Vue.js SPA Frontend)

---

## I. TỔNG QUAN HỆ THỐNG

**2AS-Worksuite** là một ứng dụng AI Voice Meeting Intelligence — hệ thống trí tuệ nhân tạo xử lý ghi âm cuộc họp, tích hợp vào hệ sinh thái CT Group. Hệ thống thực hiện **5 chức năng chính**:

| # | Chức năng | Mô tả |
|---|-----------|-------|
| 1 | **Speech-to-Text (STT)** | Dịch âm thanh → văn bản với speaker diarization |
| 2 | **Speaker Identification** | Nhận diện danh tính người nói qua voice embedding |
| 3 | **Transcript Cleaning** | Làm sạch văn bản bằng LLM (xóa từ đệm, ngập ngừng) |
| 4 | **Task Extraction** | Trích xuất nhiệm vụ/thông báo từ biên bản họp bằng AI |
| 5 | **Voice-to-Task** | Tạo task nhanh bằng giọng nói (1 lệnh voice → 1 task) |

---

## II. KIẾN TRÚC HỆ THỐNG

### 2.1 Stack Công Nghệ

```mermaid
graph TB
    subgraph Frontend["🖥️ Frontend (Vue.js SPA)"]
        App["App.vue"]
        VT["VoiceTranscribe.vue"]
        VE["VoiceEnroll.vue"]
        VTask["VoiceTask.vue"]
        MH["MeetingHistory.vue"]
        API_JS["api.js (Axios)"]
    end

    subgraph Backend["⚙️ Backend (Frappe/Python)"]
        API_PY["api.py (REST Endpoints)"]
        GEM["gemini_stt_client.py"]
        EL["elevenlabs_client.py"]
        SPK["speaker_manager.py"]
        TE["task_extractor.py (LangGraph)"]
        AU["audio_utils.py (FFmpeg)"]
        DX["docx_utils.py"]
        AL["activity_logger.py"]
        EMB["extract_embedding.py (Subprocess)"]
    end

    subgraph External["🌐 External Services"]
        GEMINI["Google Gemini API"]
        ELAPI["ElevenLabs API"]
        OPENAI["OpenAI GPT-4o"]
        CTERP["CT ERP (Worksuite API)"]
        HF["HuggingFace pyannote"]
    end

    subgraph Storage["💾 Data Layer"]
        DB["MariaDB (Frappe DocTypes)"]
        CACHE["Redis Cache"]
        FILES["File System (WAV/DOCX/XLSX)"]
    end

    Frontend -->|HTTP/REST| Backend
    GEM -->|Streaming SSE| GEMINI
    EL -->|REST| ELAPI
    TE -->|REST| OPENAI
    API_PY -->|REST| CTERP
    EMB -->|PyTorch| HF
    Backend --> Storage
```

### 2.2 Cấu Trúc DocTypes (Data Models)

| DocType | Vai trò | Trạng thái |
|---------|---------|------------|
| **Voice Meeting** | Lưu trữ cuộc họp: audio, transcript, tasks, files | Pending → Processing → Completed → Analyzed → Synced / Error |
| **Voice Speaker** | CSDL mẫu giọng nói (embedding vector + metadata) | Persistent |
| **Voice App Settings** | Singleton chứa API keys, config | Persistent |
| **VOICE Session** | Session tracking per user | Active → Completed |
| **VOICE Action Log** | Log từng hành động của user | Running → Success/Failed |
| **VOICE AI Call Log** | Log chi tiết mỗi lần gọi AI (tokens, cost) | Per-call record |
| **Voice Task** | Lưu trữ task đã trích xuất | Persistent |

---

## III. CÁC LUỒNG XỬ LÝ CHI TIẾT

### 3.1 🎙️ LUỒNG 1: Transcribe Audio (Luồng chính — Phức tạp nhất)

> **Loại:** Luồng **BẤT ĐỒNG BỘ** (Async via `frappe.enqueue` → Redis Queue)  
> **Timeout:** 3600s (1 giờ)  
> **Bên trong:** Kết hợp **SONG SONG** (ThreadPoolExecutor) + **TUẦN TỰ** (Pipeline)

```mermaid
flowchart TD
    A["👤 User Upload Audio File"] --> B["API: transcribe_audio()"]
    B --> C["Lưu File vào Frappe DB"]
    C --> D["Tạo Voice Meeting\n(status: Processing)"]
    D --> E["frappe.enqueue()\n→ Redis Long Queue"]
    E --> F["Return {status: processing,\nmeeting_name}"]
    
    E --> G["_transcribe_audio_async()"]
    
    subgraph ASYNC["⚡ Background Worker (Async)"]
        G --> H["1. convert_to_wav()\nFFmpeg → WAV 16kHz mono"]
        H --> I["2. split_audio_by_silence()\nWebRTC VAD → chunks 30 phút"]
        
        I --> J{"STT Mode?"}
        J -->|google| K["3a. call_gemini_stt()"]
        J -->|elevenlabs| L["3b. call_elevenlabs_stt()"]
        
        subgraph PARALLEL["🔀 SONG SONG (ThreadPool max 6)"]
            K --> K1["Upload chunk 1 → Gemini"]
            K --> K2["Upload chunk 2 → Gemini"]
            K --> K3["Upload chunk N → Gemini"]
            K1 --> K1R["Stream response chunk 1"]
            K2 --> K2R["Stream response chunk 2"]
            K3 --> K3R["Stream response chunk N"]
        end
        
        K1R & K2R & K3R --> M["4. Merge all segments\n(sort by timestamp)"]
        L --> M
        
        M --> N["5. Speaker Identification\n(TUẦN TỰ per speaker)"]
        N --> N1["Extract embedding\n(subprocess → pyannote)"]
        N1 --> N2["SpeakerDB.identify_ranked()\ncosine similarity ≥ 0.5"]
        N2 --> N3["Greedy Assignment\n(score cao nhất giành trước)"]
        N3 --> N4["Merge 'Người lạ'\n(Constrained Clustering)"]
        
        N4 --> O["6. Post-processing"]
        O --> O1["Lọc segment vô nghĩa"]
        O1 --> O2["Gộp segment liền kề\ncùng speaker (gap < 1.5s)"]
        O2 --> O3["Format output text"]
        
        O3 --> P["7. Update Voice Meeting\n(status: Completed)"]
        P --> Q["8. Log AI Call"]
    end
    
    F -.->|Polling| R["check_meeting_status()\n(Frontend poll mỗi 2-3s)"]
    R --> S{"status?"}
    S -->|processing| R
    S -->|success| T["🎉 Hiển thị transcript"]
    S -->|error| U["❌ Hiển thị lỗi"]

    style PARALLEL fill:#e6f3ff,stroke:#0066cc
    style ASYNC fill:#f0fff0,stroke:#009900
```

#### Chi tiết xử lý song song trong Gemini STT:

| Bước | Thực thi | Chi tiết |
|------|----------|---------|
| Upload file | **SONG SONG** nhưng có **Lock** | `_upload_lock` — mỗi lần chỉ 1 thread upload (tránh 429) + delay 1.5s |
| STT streaming | **SONG SONG** | `ThreadPoolExecutor(max_workers=6)` — tối đa 6 chunk song song |
| Wait file ACTIVE | **Tuần tự** per chunk | Poll mỗi 5s, tối đa 30 lần (150s) |
| Speaker ID | **Tuần tự** | Xử lý từng speaker một (embedding extraction là subprocess riêng) |

#### Cơ chế Smart Resume:
Khi Gemini gặp hallucination (MAX_TOKENS), hệ thống **tự động cắt phần chưa xử lý** và gọi lại:
```
Chunk bị ngáo ở giây 300/600s → Cắt audio [300s:600s] → Tạo sub-chunk → Gọi Gemini lại → Merge kết quả
```

---

### 3.2 🧹 LUỒNG 2: Clean Transcript (Làm sạch văn bản)

> **Loại:** **BẤT ĐỒNG BỘ** (frappe.enqueue → Redis Long Queue)  
> **Timeout:** 1500s  
> **Xử lý:** **TUẦN TỰ** (gọi OpenAI GPT → update DB)

```mermaid
flowchart LR
    A["User bấm 'Lọc nhiễu'"] --> B["clean_transcript() → enqueue"]
    B --> C["_clean_transcript_async()"]
    C --> D["clean_transcript_llm()\nGọi OpenAI GPT"]
    D --> E["Update Voice Meeting\n(raw_results = cleaned)"]
    E --> F["Cache kết quả\n(Redis, 24h TTL)"]
    
    A -.->|"Poll 2s"| G["check_clean_status()"]
    G --> H{"Redis cache?"}
    H -->|có| I["Return cleaned_results"]
    H -->|không| G
```

---

### 3.3 📝 LUỒNG 3: Extract Tasks (Trích xuất nhiệm vụ)

> **Loại:** **BẤT ĐỒNG BỘ** (frappe.enqueue → Redis Long Queue)  
> **Xử lý:** **TUẦN TỰ** nhưng dùng **LangGraph State Machine** (6 nodes)

```mermaid
flowchart TD
    A["User bấm 'Trích xuất Task'"] --> B["extract_tasks() → enqueue"]
    B --> C["_extract_tasks_async()"]
    
    subgraph LANGGRAPH["🤖 LangGraph Pipeline (Tuần tự)"]
        direction TB
        N1["Node 1: read_docx\nĐọc file DOCX → text"] --> CHECK1{doc_text?}
        CHECK1 -->|yes| N2["Node 2: extract_tasks\nGPT-4o-mini → JSON tasks"]
        CHECK1 -->|no| END1["END (error)"]
        
        N2 --> CHECK2{extracted_data?}
        CHECK2 -->|yes| N3["Node 3: login_frappe\nAuth token → CTERP"]
        CHECK2 -->|no| END1
        
        N3 --> CHECK3{session?}
        CHECK3 -->|yes| N4["Node 4: fetch_users\nLấy DS nhân viên"]
        CHECK3 -->|no| END1
        
        N4 --> N5["Node 4.5: fetch_projects\nLấy DS dự án + Project User"]
        N5 --> END2["END → Return results"]
    end
    
    C --> D1["1. Lấy speaker_roles từ CTERP"]
    D1 --> D2["2. save_to_docx()\nTạo biên bản họp DOCX"]
    D2 --> D3["3. extract_tasks_only()\n→ LangGraph Pipeline"]
    D3 --> LANGGRAPH
    LANGGRAPH --> D4["4. Match employees\n(Token Overlap ≥ 0.6)"]
    D4 --> D5["5. Tạo Excel (pandas)"]
    D5 --> D6["6. Update Voice Meeting\n(status: Analyzed)"]
    D6 --> D7["7. Cache kết quả (Redis)"]

    style LANGGRAPH fill:#fff3e0,stroke:#ff9800
```

#### LangGraph State Flow:

| Node | Input | Output | Conditional |
|------|-------|--------|-------------|
| `read_docx` | file_path | doc_text | → `extract` nếu có text, → `END` nếu không |
| `extract_tasks` | doc_text | extracted_data (JSON) | → `login` nếu OK, → `END` nếu lỗi |
| `login_frappe` | — | session (requests.Session) | → `fetch_users` nếu auth OK |
| `fetch_users` | session | frappe_users list | Luôn → `fetch_projects` |
| `fetch_projects` | session | frappe_projects map | Luôn → `END` |

---

### 3.4 🎤 LUỒNG 4: Voice-to-Task (Tạo task bằng giọng nói)

> **Loại:** **ĐỒNG BỘ** (xử lý ngay, không enqueue)  
> **Xử lý:** **TUẦN TỰ** hoàn toàn

```mermaid
flowchart LR
    A["User ghi âm\nlệnh voice"] --> B["voice_to_task()"]
    B --> C["1. convert_to_wav()"]
    C --> D["2. ElevenLabs STT\n→ full_text"]
    D --> E["3. Fetch Projects +\nEmployees từ CTERP"]
    E --> F["4. OpenAI GPT-4o\nParse intent → JSON"]
    F --> G{"missing_fields?"}
    G -->|có| H["Return clarification_question\n(hỏi user bổ sung)"]
    G -->|không| I["Return task data\n(đầy đủ thông tin)"]
```

**Đặc điểm nổi bật:**
- Hỗ trợ **multi-turn**: gửi `existing_task` để bổ sung thông tin qua nhiều lần nói
- Tự động gán người thực hiện = người đang đăng nhập nếu user nói "tôi", "mình"
- Tính toán ngày thông minh: "ngày mai", "tuần sau", "vài ngày nữa"

---

### 3.5 🔊 LUỒNG 5: Voice Enrollment (Đăng ký giọng nói)

> **Loại:** **ĐỒNG BỘ**  
> **Xử lý:** **TUẦN TỰ**

```mermaid
flowchart LR
    A["User thu âm/upload\nmẫu giọng nói"] --> B["enroll_voice()"]
    B --> C["convert_to_wav()"]
    C --> D["enroll_new_speaker()"]
    D --> E["Subprocess:\nextract_embedding.py"]
    E --> F["pyannote/embedding\n→ 512-dim vector"]
    F --> G["L2 normalize"]
    G --> H["SpeakerDB.add_speaker()\n→ Voice Speaker DocType"]
```

---

### 3.6 🔄 LUỒNG 6: Sync Tasks to ERP

> **Loại:** **ĐỒNG BỘ**  
> **Xử lý:** **TUẦN TỰ** với **Transactional Rollback**

```mermaid
flowchart TD
    A["User bấm\n'Đồng bộ lên Worksuite'"] --> B["sync_tasks_to_erp()"]
    B --> C["create_tasks_to_erp()"]
    C --> D["Check trùng lặp\n(subject + project + assignee)"]
    D --> E{"Trùng?"}
    E -->|có| F["Skip + Error"]
    E -->|không| G["POST /api/resource/Task\n→ CTERP"]
    G --> H["Assign user\n(frappe.desk.form.assign_to.add)"]
    H --> I{"Có lỗi?"}
    I -->|có| J["🔄 ROLLBACK\nXóa tất cả task đã tạo"]
    I -->|không| K["✅ Return report"]
```

---

## IV. BẢN ĐỒ LUỒNG DỮ LIỆU TỔNG THỂ

```mermaid
flowchart TB
    subgraph INPUT["📥 INPUT"]
        A1["Audio File\n(MP3/WAV/M4A)"]
        A2["Voice Command\n(Microphone)"]
        A3["Past Meeting\n(Từ History)"]
    end
    
    subgraph PROCESSING["⚙️ PROCESSING"]
        B1["FFmpeg\nConvert → WAV 16kHz"]
        B2["WebRTC VAD\nSplit by Silence"]
        B3["Gemini/ElevenLabs\nSTT + Diarization"]
        B4["pyannote\nSpeaker Embedding"]
        B5["SpeakerDB\nCosine Similarity"]
        B6["GPT-4o-mini\nTask Extraction"]
        B7["GPT-4o\nVoice Intent Parse"]
        B8["GPT-4o\nTranscript Clean"]
    end
    
    subgraph OUTPUT["📤 OUTPUT"]
        C1["📄 Transcript\n(Speaker-labeled text)"]
        C2["📋 Task List\n(Editable table)"]
        C3["📑 Biên bản DOCX\n(Template-based)"]
        C4["📊 Task Excel\n(pandas DataFrame)"]
        C5["🔗 ERP Tasks\n(Synced to CTERP)"]
        C6["🗣️ Speaker Profile\n(Voice DB entry)"]
    end
    
    A1 --> B1 --> B2 --> B3 --> C1
    B3 --> B4 --> B5 --> C1
    C1 --> B8 --> C1
    C1 --> B6 --> C2
    C1 --> C3
    C2 --> C4
    C2 --> C5
    A2 --> B1 --> B7 --> C2
    A2 --> B1 --> B4 --> C6
    A3 --> C1
```

---

## V. TỔ CHỨC LUỒNG: TUẦN TỰ vs SONG SONG

### 5.1 Tổng quan

| Luồng | Kiểu thực thi | Async? | Song song nội bộ? |
|-------|--------------|--------|-------------------|
| **Transcribe Audio** | Async (Redis Queue) | ✅ | ✅ 6 threads (Gemini chunks) |
| **Clean Transcript** | Async (Redis Queue) | ✅ | ❌ Tuần tự |
| **Extract Tasks** | Async (Redis Queue) | ✅ | ❌ Tuần tự (LangGraph) |
| **Voice-to-Task** | Synchronous | ❌ | ❌ Tuần tự |
| **Voice Enrollment** | Synchronous | ❌ | ❌ Tuần tự |
| **Sync to ERP** | Synchronous | ❌ | ❌ Tuần tự |
| **Frontend Polling** | Async (setInterval) | ✅ | ❌ |

### 5.2 Chi tiết Song Song trong Transcribe

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRANSCRIBE PIPELINE                          │
│                                                                 │
│  [TUẦN TỰ]  Upload audio → Convert WAV → Split chunks          │
│       │                                                         │
│       ▼                                                         │
│  [SONG SONG - ThreadPoolExecutor(6)]                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Chunk 0  │ │ Chunk 1  │ │ Chunk 2  │ │ Chunk N  │          │
│  │ Upload   │ │ Upload   │ │ Upload   │ │ Upload   │          │
│  │ (locked) │ │ (locked) │ │ (locked) │ │ (locked) │          │
│  │ Stream   │ │ Stream   │ │ Stream   │ │ Stream   │          │
│  │ Parse    │ │ Parse    │ │ Parse    │ │ Parse    │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│       │            │            │            │                  │
│       ▼            ▼            ▼            ▼                  │
│  [TUẦN TỰ]  Merge → Speaker ID → Greedy Assign → Format       │
│       │                                                         │
│       ▼                                                         │
│  [TUẦN TỰ]  Save to DB → Log                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Cơ Chế Polling (Frontend ↔ Backend)

```mermaid
sequenceDiagram
    participant F as Frontend
    participant B as Backend API
    participant Q as Redis Queue
    participant W as Background Worker
    participant C as Redis Cache
    
    F->>B: POST transcribe_audio(file)
    B->>Q: enqueue(_transcribe_audio_async)
    B-->>F: {status: "processing", meeting_name}
    
    W->>Q: Dequeue job
    W->>W: Process audio (5-60 min)
    W->>C: set_value(progress_{name})
    
    loop Polling (mỗi 2-3s)
        F->>B: GET check_meeting_status(name)
        B->>C: get_value(progress_{name})
        B-->>F: {status: "processing", progress_info}
    end
    
    W->>W: Complete processing
    W->>B: db.set_value(status="Completed")
    
    F->>B: GET check_meeting_status(name)
    B-->>F: {status: "success", results, final_text}
```

---

## VI. INTEGRATION MAP (Tích hợp bên ngoài)

```mermaid
graph LR
    subgraph APP["2AS-Worksuite"]
        API["api.py"]
    end
    
    subgraph AI["🤖 AI Services"]
        G["Google Gemini\n(STT + Diarization)"]
        E["ElevenLabs\n(STT Scribe v2)"]
        O["OpenAI GPT-4o\n(Task Extract + Clean)"]
        P["pyannote/embedding\n(Speaker Embedding)"]
    end
    
    subgraph ERP["🏢 CT ERP"]
        EMP["Employee API"]
        PROJ["Project API"]
        TASK["Task API"]
        USER["User API"]
    end
    
    subgraph HUB["🔌 CT Agent Hub"]
        ACC["check_app_access()"]
    end
    
    API -->|"Upload file + Stream SSE"| G
    API -->|"REST"| E
    API -->|"Chat Completion"| O
    API -->|"Subprocess"| P
    API -->|"REST + Token Auth"| EMP
    API -->|"REST"| PROJ
    API -->|"POST + Assign"| TASK
    API -->|"REST"| USER
    API -->|"Import"| ACC
```

---

## VII. OBSERVABILITY & LOGGING

Hệ thống sử dụng **ActivityLogger** — một utility dùng chung cho tất cả Frappe App trong CT Group:

```
Session (1 lần mở app)
  ├── Action Log 1 (transcribe_audio)
  │     ├── AI Call Log (google/speech-to-text)
  │     └── AI Call Log (elevenlabs/scribe_v2)
  ├── Action Log 2 (extract_tasks)
  │     └── AI Call Log (gpt-4o-mini)
  ├── Action Log 3 (clean_transcript)
  │     └── AI Call Log (gpt-4o)
  └── Action Log 4 (voice_to_task)
        └── AI Call Log (gpt-4o)
```

**Metrics được track:**
- `prompt_tokens`, `completion_tokens` → Token usage per model
- `duration_seconds` → Thời gian xử lý
- `elevenlabs_chars_used/remaining` → ElevenLabs quota
- `token_breakdown` (JSON) → Breakdown theo từng model
- `total_ai_calls`, `total_actions` → Aggregated per session

---

## VIII. ERROR HANDLING & RESILIENCE

| Cơ chế | Áp dụng ở | Chi tiết |
|--------|-----------|---------|
| **Retry with Exponential Backoff** | Gemini STT | 4 lần retry, delay: 5→10→20→40s + jitter |
| **Smart Resume** | Gemini STT | Khi bị hallucination, cắt phần chưa xử lý → chạy tiếp |
| **Partial Error** | Transcribe | Nếu STT xong nhưng lỗi giữa chừng → lưu phần đã có |
| **Transactional Rollback** | Sync to ERP | Nếu 1 task lỗi → xóa tất cả task đã tạo |
| **Subprocess Isolation** | Speaker Embedding | PyTorch chạy trong subprocess riêng → tránh DNNL crash trong Gunicorn |
| **Upload Lock** | Gemini chunk upload | `threading.Lock()` — chỉ 1 thread upload cùng lúc (tránh 429) |
| **Embedding Cache** | Speaker Manager | FIFO cache 64 entries → tránh gọi subprocess trùng lặp |
| **DB Rollback Guards** | Logging | Nếu log AI call lỗi → rollback DB trước khi tiếp tục |

---

## IX. SƠ ĐỒ TRẠNG THÁI VOICE MEETING

```mermaid
stateDiagram-v2
    [*] --> Pending: Tạo mới
    Pending --> Processing: enqueue transcribe
    Processing --> Completed: STT + Speaker ID xong
    Processing --> Error: Lỗi xử lý
    Processing --> Partial_Error: STT xong 1 phần
    Partial_Error --> Processing: resume_transcription()
    Completed --> Analyzed: extract_tasks() xong
    Analyzed --> Synced: sync_tasks_to_erp() xong
    Error --> Processing: Retry
```

---

## X. FRONTEND ARCHITECTURE

### 10.1 Routing (SPA)

```
/aicenter/2as-worksuite → voice_app_spa (Frappe website_route_rules)
```

### 10.2 Views & Components

| View/Component | Chức năng |
|----------------|-----------|
| `VoiceTranscribe.vue` | Upload audio, hiển thị transcript, clean, extract tasks |
| `VoiceEnroll.vue` | Thu âm/upload mẫu giọng, đăng ký Speaker DB |
| `VoiceTask.vue` | Ghi âm lệnh voice → tạo task nhanh |
| `MeetingHistory.vue` | Xem lại lịch sử cuộc họp |
| `TaskModal.vue` | Modal chỉnh sửa task trước khi sync |
| `AppSidebar.vue` | Navigation sidebar |

### 10.3 State Management

Sử dụng **Vue 3 Composition API** với shared reactive state qua `useVoiceApp.js`:
- Không dùng Vuex/Pinia — state được export trực tiếp từ composable
- Polling status qua `setInterval` + API calls

---

## XI. TÓM TẮT SỐ LƯỢNG LUỒNG

| Metric | Giá trị |
|--------|---------|
| **Tổng số luồng chính** | **6 luồng** |
| **Luồng bất đồng bộ (Async)** | **3** (Transcribe, Clean, Extract) |
| **Luồng đồng bộ (Sync)** | **3** (Voice-to-Task, Enroll, Sync ERP) |
| **Luồng có xử lý song song bên trong** | **1** (Transcribe → 6 threads) |
| **Luồng hoàn toàn tuần tự** | **5** |
| **Tổng số External API tích hợp** | **5** (Gemini, ElevenLabs, OpenAI, CTERP, pyannote) |
| **Tổng số REST endpoints** | **~20** endpoints (`@frappe.whitelist`) |
| **Tổng số DocTypes** | **7** |

> [!IMPORTANT]
> Điểm mấu chốt: Hệ thống sử dụng mô hình **"Enqueue + Polling"** cho các tác vụ nặng (STT, Extract). Frontend liên tục poll backend qua REST API (mỗi 2-3s) để kiểm tra trạng thái. **Không sử dụng WebSocket** — toàn bộ giao tiếp real-time dựa trên polling + Redis cache.
