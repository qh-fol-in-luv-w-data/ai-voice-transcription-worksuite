import os
import time
import json
import re
import random
import threading
import requests as _requests
import concurrent.futures
from .audio_utils import get_duration
from .constants import get_gemini_api_key, get_gemini_model

UPLOAD_URL      = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GENERATE_URL    = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FILE_STATUS_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"
STREAM_URL      = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"

_RETRY_MAX        = 4   # số lần thử tối đa khi gặp 429
_RETRY_BASE_DELAY = 5   # giây, tăng gấp đôi mỗi lần: 5 → 10 → 20 → 40

# Thread-local session để mỗi thread có connection pool riêng
_thread_local = threading.local()

def _get_session():
    if not hasattr(_thread_local, "session"):
        _thread_local.session = _requests.Session()
    return _thread_local.session

def _get_gemini_model():
    try:
        import frappe
        val = frappe.conf.get("gemini_model")
        if val: return val
    except Exception: pass
    return get_gemini_model()

def _get_api_key():
    try:
        import frappe
        val = frappe.conf.get("gemini_api_key")
        if val: return val
    except Exception: pass
    return get_gemini_api_key()


def _get_auth_headers_and_query(api_key):
    """Xử lý chứng thực cho cả API Key thường và OAuth Token (Google Cloud)."""
    import frappe
    try:
        project_id = frappe.conf.get("gemini_project_id")
    except Exception:
        project_id = "562803079059"
    if not project_id:
        project_id = "562803079059"

    if api_key.startswith("ya29."):
        # Đây mới thực sự là OAuth Token
        return "", {
            "Authorization": f"Bearer {api_key}",
            "x-goog-user-project": project_id
        }
    else:
        # API Key bình thường (bao gồm cả chuẩn cũ AIza... và chuẩn mới AQ...)
        return f"?key={api_key}", {
            "x-goog-user-project": project_id
        }

def _upload_file_data(wav_path, api_key):
    """Upload file lên Gemini, trả về (file_uri, file_name) ngay khi upload xong (chưa chờ ACTIVE)."""
    session = _get_session()
    file_size = os.path.getsize(wav_path)
    
    query, auth_headers = _get_auth_headers_and_query(api_key)
    
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": "audio/wav",
        "Content-Type": "application/json",
        **auth_headers
    }

    for attempt in range(_RETRY_MAX):
        try:
            init = session.post(
                f"{UPLOAD_URL}{query}",
                headers=headers,
                json={"file": {"display_name": os.path.basename(wav_path)}},
                timeout=120,
            )
            if init.status_code == 429 and attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                print(f"[Gemini STT] 429 upload init, thử lại {attempt + 1}/{_RETRY_MAX - 1} sau {delay:.1f}s...")
                time.sleep(delay)
                continue
            init.raise_for_status()
            break
        except (_requests.exceptions.RequestException, IOError) as e:
            if attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                print(f"[Gemini STT] Lỗi kết nối (init upload) ({type(e).__name__}), thử lại sau {delay:.1f}s...")
                time.sleep(delay)
                continue
            raise

    upload_url = init.headers["X-Goog-Upload-URL"]

    with open(wav_path, "rb") as f:
        data = f.read()

    for attempt in range(_RETRY_MAX):
        try:
            upload_resp = session.post(
                upload_url,
                headers={
                    "Content-Length": str(file_size),
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                data=data,
                timeout=600,
            )
            if upload_resp.status_code == 429 and attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                print(f"[Gemini STT] 429 upload data, thử lại {attempt + 1}/{_RETRY_MAX - 1} sau {delay:.1f}s...")
                time.sleep(delay)
                continue
            upload_resp.raise_for_status()
            break
        except (_requests.exceptions.RequestException, IOError) as e:
            if attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                print(f"[Gemini STT] Lỗi kết nối (upload data) ({type(e).__name__}), thử lại sau {delay:.1f}s...")
                time.sleep(delay)
                continue
            raise

    file_info = upload_resp.json()["file"]
    file_uri  = file_info["uri"]
    file_name = file_info["name"]
    print(f"[Gemini STT] Uploaded → {file_uri}, chờ ACTIVE...")
    return file_uri, file_name


def _wait_file_active(file_name, file_uri, api_key):
    """Poll cho đến khi file ACTIVE rồi mới trả về."""
    session = _get_session()
    query, auth_headers = _get_auth_headers_and_query(api_key)
    for _ in range(30):
        sr = session.get(
            f"{FILE_STATUS_URL.format(name=file_name)}{query}",
            headers=auth_headers,
            timeout=30,
        )
        if sr.status_code in [403, 429, 500, 502, 503, 504]:
            print(f"[Gemini STT] File status {sr.status_code}, retrying...")
            time.sleep(5 + random.uniform(0, 2))
            continue
        sr.raise_for_status()
        state = sr.json().get("state", "")
        if state == "ACTIVE":
            print(f"[Gemini STT] File ACTIVE: {file_uri}")
            return
        if state == "FAILED":
            raise Exception(f"Gemini file processing FAILED: {file_name}")
        time.sleep(5)
    raise Exception("Gemini file processing timeout sau 200s")


def _upload_file(wav_path, api_key):
    """Upload và chờ ACTIVE (wrapper để tương thích ngược)."""
    file_uri, file_name = _upload_file_data(wav_path, api_key)
    _wait_file_active(file_name, file_uri, api_key)
    return file_uri, file_name


def _delete_file(file_name, api_key):
    """Xóa file khỏi Gemini File API sau khi dùng xong."""
    try:
        session = _get_session()
        query, auth_headers = _get_auth_headers_and_query(api_key)
        resp = session.delete(
            f"{FILE_STATUS_URL.format(name=file_name)}{query}",
            headers=auth_headers,
            timeout=30,
        )
        if resp.status_code in (200, 204):
            print(f"[Gemini STT] Deleted: {file_name}")
        else:
            print(f"[Gemini STT] Delete failed {resp.status_code}: {file_name}")
    except Exception as e:
        print(f"[Gemini STT] Delete error: {e}")


def _call_gemini_stream(file_uri, api_key, prompt, model_name=None, max_tokens=12000):
    """Gọi Gemini stream API, trả về (segments, usage_dict, error_str|None)."""
    session = _get_session()
    if not model_name:
        model_name = _get_gemini_model()

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"file_data": {"mime_type": "audio/wav", "file_uri": file_uri}},
                {"text": prompt},
            ]
        }],
        "generation_config": {
            "temperature": 0.3,
            "response_mime_type": "application/json",
            "maxOutputTokens": max_tokens,
        },
    }

    full_text       = ""
    total_in        = 0
    total_out       = 0
    total_tokens    = 0
    thoughts_tokens = 0
    cached_tokens   = 0
    finish_reason   = None
    query, auth_headers = _get_auth_headers_and_query(api_key)
    url = f"{STREAM_URL.format(model=model_name)}{query}"
    url += "&alt=sse" if "?" in url else "?alt=sse"

    for attempt in range(_RETRY_MAX):
        print(f"[Gemini STT] Streaming attempt {attempt + 1}/{_RETRY_MAX} (model={model_name})...")
        try:
            resp = session.post(url, json=payload, headers=auth_headers, timeout=1800, stream=True)

            if resp.status_code in [403, 429, 500, 502, 503, 504]:
                if attempt < _RETRY_MAX - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                    print(f"[Gemini STT] {resp.status_code} stream, thử lại sau {delay:.1f}s...")
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()

            full_text       = ""
            total_in        = 0
            total_out       = 0
            total_tokens    = 0
            thoughts_tokens = 0
            cached_tokens   = 0
            finish_reason   = None

            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else raw_line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    parsed_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                chunks_list = parsed_data if isinstance(parsed_data, list) else [parsed_data]
                for chunk in chunks_list:
                    if not isinstance(chunk, dict):
                        continue
                    usage = chunk.get("usageMetadata", {})
                    if usage:
                        total_in      = usage.get("promptTokenCount", total_in)
                        total_out     = usage.get("candidatesTokenCount", total_out)
                        total_tokens  = usage.get("totalTokenCount", total_tokens)
                        cached_tokens = usage.get("cachedContentTokenCount", cached_tokens)

                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue
                    cand = candidates[0]
                    finish_reason = cand.get("finishReason", finish_reason)
                    parts = cand.get("content", {}).get("parts", [])
                    for part in parts:
                        if not part.get("thought", False) and "text" in part:
                            full_text += part["text"]

            break  # stream đọc xong thành công

        except (_requests.exceptions.RequestException, IOError) as e:
            if attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(1, 5)
                print(f"[Gemini STT] Connection error ({type(e).__name__}), thử lại sau {delay:.1f}s...")
                time.sleep(delay)
            else:
                raise

    billable_out = max(total_tokens - total_in, total_out + thoughts_tokens)
    total_tokens = max(total_tokens, total_in + billable_out)
    usage_result = {
        "prompt_tokens":     total_in,
        "completion_tokens": billable_out,
        "tokens_used":       total_tokens,
        "candidate_tokens":  total_out,
        "thoughts_tokens":   thoughts_tokens,
        "cached_tokens":     cached_tokens,
        "model":             f"google/{model_name}",
    }

    PRICE_IN  = 1.50 / 1_000_000
    PRICE_OUT = 9.00 / 1_000_000
    cost = total_in * PRICE_IN + billable_out * PRICE_OUT
    print(
        f"💰 [Gemini STT] model={model_name} | "
        f"in={total_in:,} out={billable_out:,} (think={thoughts_tokens}) | "
        f"total={total_tokens:,} tokens | cost=~${cost:.4f} USD | finish={finish_reason}"
    )

    if finish_reason == "MAX_TOKENS":
        print("[Gemini STT] ⚠️ MAX_TOKENS — Phát hiện vòng lặp ảo giác.")
        return _parse_gemini_response(full_text), usage_result, "HALLUCINATION_DETECTED"
    elif finish_reason == "SAFETY":
        return [], usage_result, "Safety filter rejected content"

    if not full_text:
        return [], usage_result, f"Gemini không trả về text (finish={finish_reason})"

    return _parse_gemini_response(full_text), usage_result, None


def _build_prompt(num_speakers, language, custom_vocabulary=""):
    lang_note    = "tiếng Việt" if language in ("vi", "vi-VN") else language
    speaker_note = (
        f"Cuộc họp có KHOẢNG {num_speakers} người tham dự. Hãy phân biệt các giọng nói (Speaker 1, Speaker 2... tối đa {num_speakers} người)."
        if num_speakers else
        "Cuộc họp có thể có nhiều người tham dự."
    )
    custom_vocab_note = f"\nTừ vựng người dùng bổ sung: {custom_vocabulary}" if custom_vocabulary else ""

    return f"""Bạn là chuyên gia phiên âm và biên tập biên bản họp. Nhiệm vụ: xử lý file ghi âm cuộc họp nội bộ bằng {lang_note} và trả ra transcript đã được làm sạch hoàn toàn.

━━━ BƯỚC 1: NHẬN DẠNG GIỌNG NÓI & TÁCH NGƯỜI NÓI (DIARIZATION) ━━━
- Transcribe TOÀN BỘ nội dung từ đầu đến cuối file — KHÔNG được bỏ sót bất kỳ lượt nói nào.
- LƯU Ý SỐ LƯỢNG NGƯỜI NÓI: {speaker_note}
- KHÔNG ĐƯỢC TỰ BỊA ĐẶT LỜI THOẠI. Chỉ ghi chép những gì nghe được.
- ĐÂY LÀ YÊU CẦU QUAN TRỌNG NHẤT: BẠN PHẢI PHÂN BIỆT ĐƯỢC CÁC GIỌNG NÓI KHÁC NHAU. MỖI LƯỢT ĐỔI NGƯỜI NÓI (dù chỉ là tiếng xen ngang "Đúng rồi", "Ok") = 1 ENTRY JSON RIÊNG BIỆT.
- NẾU CÓ 2 NGƯỜI NÓI ĐÈ LÊN NHAU (OVERLAP) HOẶC CÃI NHAU: TUYỆT ĐỐI KHÔNG GỘP CHUNG CHỮ VÀO 1 ENTRY. Bắt buộc phải tách lời của người A và người B thành 2 entry nối tiếp nhau. LỖI NGHIÊM TRỌNG NHẤT LÀ NHÉT LỜI CỦA 2 NGƯỜI VÀO CÙNG 1 CÂU NÓI CỦA 1 NGƯỜI.
- CÂU HỎI và CÂU TRẢ LỜI luôn là 2 entry riêng biệt — người hỏi và người trả lời KHÔNG bao giờ được gộp chung.
- Nếu một đoạn có nhiều người nói liên tục, HÃY CẮT NHỎ THÀNH NHIỀU ENTRY LIÊN TIẾP.
- TUYỆT ĐỐI KHÔNG TRẢ VỀ 1 ENTRY KÉO DÀI NHIỀU PHÚT. Nếu một người nói liên tục quá lâu, BẮT BUỘC PHẢI CẮT NHỎ lời nói của họ thành nhiều entry liên tiếp (mỗi entry khoảng 3-5 câu).
- Hãy đối chiếu ÂM THANH THỰC TẾ: cao độ giọng, tốc độ nói, chất giọng. Nếu trong một đoạn liên tục có sự thay đổi âm sắc (ví dụ từ giọng nam trầm sang giọng nam cao, hoặc giọng nữ) → PHẢI TẠO ENTRY MỚI NGAY TẠI ĐIỂM ĐÓ.
- KHÔNG suy đoán speaker theo ngữ cảnh (ai đặt câu hỏi thì ai trả lời) — CHỈ ĐƯỢC PHÉP dựa vào sự thay đổi thực tế của sóng âm/chất giọng mà bạn nghe được.
- Bỏ qua tạp âm, tiếng ồn, tiếng động nền.
- CỰC KỲ QUAN TRỌNG: Nếu đoạn âm thanh LÀ KHOẢNG LẶNG, CHỈ CÓ TẠP ÂM, HOẶC KHÔNG CÓ TIẾNG NGƯỜI NÓI, TUYỆT ĐỐI KHÔNG ĐƯỢC TỰ BỊA RA LỜI NÓI HOẶC LẶP LẠI LỜI CŨ. HÃY TRẢ VỀ MẢNG RỖNG [] NẾU KHÔNG NGHE THẤY GÌ.
- NGUYÊN TẮC CHỐNG LẶP (ANTI-LOOP): Khi đã transcribe hết tiếng người nói thực sự trong audio, BẠN PHẢI DỪNG LẠI NGAY LẬP TỨC và đóng mảng JSON `]`. TUYỆT ĐỐI KHÔNG được lặp lại một câu nói nhiều lần. Nếu bạn thấy mình chuẩn bị viết lại cùng một câu (hoặc một cụm từ) đến lần thứ 2 liên tiếp mà không có tiếng nói thực sự tương ứng, hãy LẬP TỨC ĐÓNG JSON và ngắt luồng.

━━━ BƯỚC 2: LÀM SẠCH VĂN BẢN ━━━
Chỉ xoá các từ/âm KHÔNG mang thông tin BÊN TRONG câu, KHÔNG được xoá cả entry:
- Xoá từ đệm/ngập ngừng: "ừm", "ờ", "à", "thì là", "ý là", "tức là", "kiểu như", "vậy á", "nha anh", "đó nha", "nghen"
- Xoá lặp từ do ngập ngừng: "cái cái cái" → bỏ, "nó nó nó" → "nó", "các ảnh các ảnh" → "các ảnh", v.v.
- Xoá câu chỉ là filler/xác nhận không có thông tin: "dạ", "vâng", "okay", "ừ", "dạ em hiểu rồi", "được anh"
- Viết lại thành câu hoàn chỉnh, dấu câu chuẩn, viết hoa đầu câu
- TUYỆT ĐỐI GIỮ ĐÚNG NGHĨA GỐC — không thêm, không bịa, không suy diễn, không tóm tắt
- Giữ code-switching Việt-Anh (không dịch thuật ngữ tiếng Anh)

━━━ TỪ VỰNG ĐẶC BIỆT (nhận dạng chính xác) ━━━
Tập đoàn: CT Group, CT Corp, CTM, CTEC, CT UAV, CT Semiconductor, CT Modulex, Modulex, GASCO, DAIT, VGCT, CCTPA, Carbondo, Airbility
Dự án/tòa nhà: M1, M2, M3, Metrostar, Simland, Minh Hưng Quảng Trị
Hệ thống: 2AS, Worksuite, iMaster, ERP, CRM, NDT15, LAE, LAE 1, OSAT, CarbonFly, green bond, carbon credit, eVTOL, LiDAR
AI/Tech: AI, AGI, LLM, GPT, ChatGPT, Claude, Gemini, ElevenLabs, RAG, vector, embedding, fine-tuning, diarization
Tài chính: green bond, CCTPA, carbon credit, ESG, IPO, M&A{custom_vocab_note}

━━━ OUTPUT FORMAT ━━━
Trả về JSON array thuần (KHÔNG markdown, KHÔNG giải thích, KHÔNG text ngoài JSON):
[
  {{"speaker": "Speaker 1", "start": 0.0, "end": 8.5, "text": "nội dung đã làm sạch"}},
  {{"speaker": "Speaker 2", "start": 8.8, "end": 15.2, "text": "nội dung đã làm sạch"}}
]
QUAN TRỌNG: "start" và "end" là số GIÂY (seconds) tính từ đầu file, KHÔNG phải phút. Ví dụ: 1 phút 30 giây = 90.0, không phải 1.5."""


def _parse_gemini_response(text):
    """Extract JSON array từ Gemini response."""
    text = re.sub(r"^```(?:json)?\s*|```\s*$", "", text.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    text_to_parse = match.group() if match else text

    try:
        return json.loads(text_to_parse)
    except json.JSONDecodeError as e:
        print(f"[Gemini STT] Lỗi JSON: {e}. Đang thử cứu phần đã có...")
        print(f"[Gemini STT] Raw text (first 500 chars): {text[:500]}...")
        last_brace = text_to_parse.rfind('}')
        if last_brace != -1:
            fixed = text_to_parse[:last_brace + 1]
            if not fixed.strip().startswith('['):
                fixed = '[' + fixed
            fixed += ']'
            try:
                rescued = json.loads(fixed)
                print(f"[Gemini STT] Cứu được {len(rescued)} segments.")
                return rescued
            except Exception as e2:
                print(f"[Gemini STT] Không thể cứu JSON: {e2}")
        return []


def _parse_time(val):
    """Parse timestamp: float giây, 'M:SS', hoặc 'H:M:SS' từ Gemini."""
    try:
        return float(val)
    except (ValueError, TypeError):
        parts = str(val).split(':')
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except ValueError:
            pass
        return 0.0


def _segments_to_raw_words(segments, file_duration=None):
    """Convert Gemini segments → raw_words format tương thích pipeline."""
    segments = [s for s in segments if isinstance(s, dict)]
    if not segments:
        return []

    raw_start = segments[0].get("start")
    raw_end   = segments[-1].get("end")
    print(f"[Gemini STT] Raw timestamps sample — first.start={raw_start!r} last.end={raw_end!r}")

    parsed = []
    for seg in segments:
        start = _parse_time(seg.get("start", 0))
        end   = _parse_time(seg.get("end", start + 1))
        parsed.append((start, end, seg))

    raw_words = []
    for start, end, seg in parsed:
        words = seg.get("text", "").split()
        if not words:
            continue
        step = (end - start) / len(words) if len(words) > 1 else (end - start)
        spk  = seg.get("speaker", "Speaker 1").replace(" ", "_").lower()
        for i, w in enumerate(words):
            raw_words.append({
                "text":       w,
                "start":      round(start + i * step, 2),
                "end":        round(start + (i + 1) * step, 2),
                "speaker_id": spk,
            })
    return raw_words


def _words_to_segments(raw_words):
    segments = []
    cur = None
    for w in raw_words:
        # Tách segment mới nếu đổi speaker HOẶC khoảng cách giữa 2 chữ > 1.5s
        if cur is None or cur["speaker_id"] != w["speaker_id"] or (w["start"] - cur["end"]) > 1.5:
            if cur: segments.append(cur)
            cur = {"start": w["start"], "end": w["end"],
                   "speaker_id": w["speaker_id"], "text": w["text"]}
        else:
            cur["end"]   = w["end"]
            cur["text"] += " " + w["text"]
    if cur: segments.append(cur)
    return segments


def call_gemini_stt(chunks_info: list, chunk_update_cb=None, language: str = "vi", num_speakers: int = None,
                    custom_vocabulary: str = "", progress_callback=None, existing_segments=None):
    """
    Google Gemini STT với speaker diarization (hỗ trợ chunking cho file dài).
    Dùng requests + ThreadPoolExecutor (tương thích Frappe gevent worker).
    Trả về: (segments, raw_words, full_text, error, chars_used, chars_remaining)
    """
    model_name = _get_gemini_model()
    api_key    = _get_api_key()

    if not api_key:
        return [], [], "", "Chưa cấu hình Gemini API Key trong Voice App Settings", 0, 0
    if not model_name:
        return [], [], "", "Chưa cấu hình Gemini Model trong Voice App Settings", 0, 0

    try:
        from .audio_utils import split_audio_by_silence
        print(f"[Gemini STT] Xử lý {len(chunks_info)} chunks, lang={language}, speakers={num_speakers}")
        prompt = _build_prompt(num_speakers, language, custom_vocabulary)

        chunks = chunks_info
        if progress_callback:
            progress_callback(20, f"Đang xử lý song song {len(chunks)} đoạn âm thanh...")

        all_segments  = []
        all_raw_words = []
        all_full_text = ""

        # Tính chunk đã done để resume (nếu có existing_segments)
        completed_chunks = set()
        if existing_segments:
            for s in existing_segments:
                if 'speaker_id' in s and s['speaker_id'].startswith('c') and '_' in s['speaker_id']:
                    try:
                        chunk_idx = int(s['speaker_id'].split('_')[0][1:])
                        completed_chunks.add(chunk_idx)
                    except: pass

        import threading
        _upload_lock = threading.Semaphore(4)

        def _process_single_chunk(chunk_dict, is_subchunk=False, dense_subchunk_offset=0.0):
            idx = chunk_dict.get("idx", 0)
            original_chunk_wav = chunk_dict.get("wav")
            current_wav = original_chunk_wav
            offset = chunk_dict.get("offset", 0.0)
            mappings = chunk_dict.get("mappings", [])
            chunk_name = chunk_dict.get("name", f"CHUNK_{idx}")

            try:
                if chunk_update_cb and not is_subchunk:
                    chunk_update_cb(chunk_name, "Processing", None, None, None, 0)

                if not is_subchunk and idx in completed_chunks:
                    print(f"[Gemini STT] Bỏ qua chunk {idx+1}/{len(chunks)} vì đã hoàn thành.")
                    return idx, None, None, None, None, None

                if is_subchunk:
                    print(f"[Gemini STT]   -> Sub-chunk {idx} - offset: {offset:.1f}s")
                else:
                    print(f"[Gemini STT] Bắt đầu chunk {idx+1}/{len(chunks)} - offset: {offset:.1f}s")

                chunk_duration = get_duration(current_wav)

                # Upload với Semaphore 4
                with _upload_lock:
                    file_uri, file_name = _upload_file(current_wav, api_key)

                chunk_error = None
                try:
                    gemini_segments, chunk_usage, chunk_error = _call_gemini_stream(
                        file_uri, api_key, prompt, model_name, max_tokens=65536
                    )
                    if chunk_error and chunk_error != "HALLUCINATION_DETECTED":
                        print(f"[Gemini STT] Error on chunk {idx+1}: {chunk_error}")
                        return idx, None, None, None, chunk_usage, chunk_error
                finally:
                    if not (chunk_error == "HALLUCINATION_DETECTED" and not is_subchunk):
                        _delete_file(file_name, api_key)
                        if current_wav != original_chunk_wav:
                            try: os.remove(current_wav)
                            except: pass
                        # Do NOT remove original_chunk_wav, handled by api.py Voice Meeting Chunk records

                if not gemini_segments:
                    return idx, [], [], "", chunk_usage, None

                # Lọc ảo giác lặp
                clean_segments = []
                loop_count = 0
                for seg in gemini_segments:
                    if not isinstance(seg, dict): continue
                    text = seg.get("text", "").strip()
                    if not text: continue
                    try:
                        seg_start = _parse_time(seg.get("start", 0))
                    except:
                        seg_start = 0
                    if seg_start > chunk_duration + 10:
                        break
                    if clean_segments and text == clean_segments[-1].get("text", "").strip():
                        loop_count += 1
                        if loop_count >= 3:
                            break
                    else:
                        loop_count = 0
                        clean_segments.append(seg)

                if not clean_segments:
                    return idx, [], [], "", chunk_usage, None

                raw_words = _segments_to_raw_words(clean_segments, file_duration=chunk_duration)
                
                # Hàm map thời gian đặc ruột về thời gian gốc
                def map_time(t_val):
                    t = _parse_time(t_val)
                    if is_subchunk:
                        t += dense_subchunk_offset
                    if mappings:
                        for m in mappings:
                            if m["dense_start"] <= t <= m["dense_end"]:
                                return m["orig_start"] + (t - m["dense_start"])
                        if t < mappings[0]["dense_start"]: return mappings[0]["orig_start"]
                        return mappings[-1]["orig_end"]
                    return t + offset

                import copy
                segments = copy.deepcopy(clean_segments)
                for seg in segments:
                    # Đảm bảo có speaker_id chuẩn hóa
                    if "speaker_id" not in seg:
                        seg["speaker_id"] = seg.get("speaker", "Speaker 1").replace(" ", "_").lower()
                    # Offset timestamps & đánh dấu chunk index
                    seg["start"]      = round(map_time(seg.get("start", 0)), 2)
                    seg["end"]        = round(map_time(seg.get("end", 0)), 2)
                    seg["speaker_id"] = f"c{idx}_{seg['speaker_id']}"
                    seg["speaker"]    = f"c{idx}_{seg.get('speaker', 'Speaker 1')}"

                for w in raw_words:
                    w["start"]      = round(map_time(w["start"]), 2)
                    w["end"]        = round(map_time(w["end"]), 2)
                    w["speaker_id"] = f"c{idx}_{w['speaker_id']}"

                chunk_text = " ".join(s.get("text", "") for s in clean_segments)

                # Smart Resume: nếu bị hallucination giữa chừng, cắt phần còn lại chạy tiếp
                if chunk_error == "HALLUCINATION_DETECTED" and not is_subchunk:
                    last_valid_ts = _parse_time(clean_segments[-1].get("end", 0))
                    if chunk_duration - last_valid_ts > 15:
                        print(f"[Gemini STT] ⚠️ Chunk {idx+1} ngáo ở giây {last_valid_ts:.1f}/{chunk_duration:.1f}s. Kích hoạt Smart Resume...")
                        import pydub
                        audio = pydub.AudioSegment.from_wav(current_wav)
                        resume_audio = audio[int(last_valid_ts * 1000):]
                        resume_wav = current_wav.replace(".wav", f"_{idx}_resume.wav")
                        resume_audio.export(resume_wav, format="wav")

                        _, r_segs, r_words, r_txt, r_use, r_err = _process_single_chunk(
                            {"idx": f"{idx}_resume", "wav": resume_wav, "offset": offset, "mappings": mappings, "name": chunk_name}, 
                            is_subchunk=True, dense_subchunk_offset=last_valid_ts
                        )

                        try: os.remove(resume_wav)
                        except: pass

                        if r_use:
                            for k in chunk_usage:
                                if k in r_use: chunk_usage[k] += r_use.get(k, 0)

                        if r_segs: segments.extend(r_segs)
                        if r_words: raw_words.extend(r_words)
                        if r_txt:   chunk_text += " " + r_txt

                if chunk_update_cb and not is_subchunk:
                    chunk_update_cb(chunk_name, "Completed", segments, raw_words, None, chunk_usage.get("tokens_used", 0))

                return idx, segments, raw_words, chunk_text, chunk_usage, None

            except Exception as e:
                import traceback
                traceback.print_exc()
                if chunk_update_cb and not is_subchunk:
                    chunk_update_cb(chunk_dict.get("name", ""), "Error", None, None, str(e), 0)
                return idx, None, None, None, None, str(e)

        # Chạy tất cả chunk song song
        completed_count = 0
        total_chunks    = len(chunks)
        results         = [None] * total_chunks
        total_in_all    = 0
        total_out_all   = 0
        total_tok_all   = 0
        chunk_errors    = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_idx = {
                executor.submit(_process_single_chunk, chunk_dict): chunk_dict.get("idx", i)
                for i, chunk_dict in enumerate(chunks)
            }

            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    res_idx, segments, raw_words, chunk_text, chunk_usage, err_msg = future.result()
                    if err_msg:
                        chunk_errors.append(f"Chunk {idx+1}: {err_msg}")
                    results[res_idx] = (segments, raw_words, chunk_text)
                    if chunk_usage:
                        total_in_all  += chunk_usage.get("prompt_tokens", 0)
                        total_out_all += chunk_usage.get("completion_tokens", 0)
                        total_tok_all += chunk_usage.get("tokens_used", 0)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    results[idx] = (None, None, None)
                    chunk_errors.append(f"Chunk {idx+1}: {str(e)}")

                completed_count += 1
                if progress_callback:
                    pct = int((completed_count / total_chunks) * 100)
                    progress_callback(pct, f"Đang xử lý: xong {completed_count}/{total_chunks} đoạn...")

        for res in results:
            if not res: continue
            segments, raw_words, chunk_text = res
            if segments and raw_words:
                all_segments.extend(segments)
                all_raw_words.extend(raw_words)
                all_full_text += " " + chunk_text

        # Gộp lại existing segments đã hoàn thành trước đó (resume)
        if existing_segments:
            for s in existing_segments:
                if 'speaker_id' in s and s['speaker_id'].startswith('c') and '_' in s['speaker_id']:
                    try:
                        chunk_idx = int(s['speaker_id'].split('_')[0][1:])
                        if chunk_idx in completed_chunks:
                            all_segments.append(s)
                            if 'text' in s:
                                all_full_text += " " + s['text']
                    except: pass

        all_segments.sort(key=lambda x: x.get('start', 0))

        if chunk_errors:
            error_details = " | ".join(chunk_errors)
            return all_segments, all_raw_words, all_full_text.strip(), \
                   f"Lỗi xử lý file (Gemini): {error_details}", total_in_all, total_out_all

        if not all_segments:
            return [], [], "", "Gemini không nhận ra giọng nói trong file (file trống, nhiễu hoặc sai format).", 0, 0

        n_spk = len(set(s.get("speaker_id", "") for s in all_segments))
        PRICE_IN  = 1.50 / 1_000_000
        PRICE_OUT = 9.00 / 1_000_000
        total_cost = total_in_all * PRICE_IN + total_out_all * PRICE_OUT
        print(
            f"[Gemini STT] ✅ DONE: {len(all_segments)} segments, {n_spk} speakers, {len(chunks)} chunks\n"
            f"💰 [Gemini STT] TỔNG CHI PHÍ FILE: "
            f"in={total_in_all:,} + out={total_out_all:,} = {total_tok_all:,} tokens | "
            f"cost=~${total_cost:.4f} USD ({len(chunks)} chunks)"
        )
        return all_segments, all_raw_words, all_full_text.strip(), None, total_in_all, total_out_all

    except Exception as e:
        import traceback
        traceback.print_exc()
        return [], [], "", f"Lỗi Gemini STT: {e}", 0, 0
