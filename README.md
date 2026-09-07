# 2AS WorkSuite - AI Voice Transcription & Task Automation

Chuyển audio cuộc họp tiếng Việt thành biên bản có tên người nói, tự sinh task và đồng bộ vào CTERP (WorkSuite). Có thêm **MCP server** để ChatGPT / MCP client bất kỳ xem lại transcript.

- Repo: [qh-fol-in-luv-w-data/ai-voice-transcription-worksuite](https://github.com/qh-fol-in-luv-w-data/ai-voice-transcription-worksuite)
- Frappe app: `voice_app`

## Tính năng chính

- Speech-to-Text tiếng Việt / tiếng Anh: **ElevenLabs Scribe** (mặc định) hoặc **Google Gemini STT**.
- Diarization + nhận diện người nói: enroll giọng, so khớp embedding (SpeechBrain 192-dim qua embedding service riêng).
- Auto-enroll khi phát hiện giọng mới, UI map thủ công khi cần.
- Trích xuất task tự động bằng LangGraph + GPT-4o (người thực hiện + hạn).
- Xuất biên bản Word / Excel theo mẫu, lọc lấp liếm.
- MCP server (`voice_app/mcp_server/`): expose transcript qua Model Context Protocol cho AI assistant.

## Yêu cầu

- Frappe Bench v15, Python 3.10+, Node.js 18+, `ffmpeg`.
- API keys: `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` (nếu dùng ElevenLabs), `HF_TOKEN` (tải pyannote lần đầu), Google credentials JSON (nếu dùng Gemini STT).
- Embedding service nội bộ (SpeechBrain, mặc định `http://192.168.90.245:8015`), cấu hình qua Voice App Settings.

## Cài đặt

```bash
cd frappe-bench
bench get-app https://github.com/qh-fol-in-luv-w-data/ai-voice-transcription-worksuite.git --branch master
bench --site <site> install-app voice_app
```

Tạo `.env` tại `apps/voice_app/voice_app/.env`:

```env
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
HF_TOKEN=hf_...
```

Frontend:

```bash
cd apps/voice_app/frontend
npm install && npm run dev -- --host
```

Chạy backend: `bench start`.

## MCP server (tuỳ chọn)

```bash
cd apps/voice_app/voice_app/mcp_server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
VOICE_APP_BASE_URL=http://<site>:8002 .venv/bin/python server.py
```

Server listen `http://127.0.0.1:8010/mcp`, xác thực bằng Frappe API key + secret (mỗi user tự tạo trong `My Settings → API Access`). Cung cấp 2 tool: `voice_app_list_meetings` và `voice_app_get_meeting_transcript`.

## License

MIT
