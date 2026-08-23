import os
import time
import json
import re
import secrets
import threading
import requests as _requests
import concurrent.futures
from contextlib import suppress
from .audio_utils import get_duration
from .constants import get_gemini_api_key, get_gemini_model, get_gemini_stt_max_output_tokens

UPLOAD_URL      = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GENERATE_URL    = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FILE_STATUS_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"
STREAM_URL      = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"

_RETRY_MAX        = 4   # số lần thử tối đa khi gặp 429
_RETRY_BASE_DELAY = 5   # giây, tăng gấp đôi mỗi lần: 5 → 10 → 20 → 40
_SECURE_RANDOM = secrets.SystemRandom()

# Thread-local session để mỗi thread có connection pool riêng
_thread_local = threading.local()

def _parse_log(message, log_cb=None):
    print(message)
    if log_cb:
        with suppress(Exception):
            log_cb(message)

def _get_session():
    if not hasattr(_thread_local, "session"):
        _thread_local.session = _requests.Session()
    return _thread_local.session

def _retry_delay(attempt, low=1, high=5):
    return _RETRY_BASE_DELAY * (2 ** attempt) + _SECURE_RANDOM.uniform(low, high)

def _get_gemini_model():
    try:
        import frappe
        val = frappe.conf.get("gemini_model")
        if val: return val
    except Exception as exc:
        print(f"[Gemini STT] Cannot read gemini_model from frappe.conf: {exc}")
    return get_gemini_model()

def _get_api_key():
    try:
        import frappe
        val = frappe.conf.get("gemini_api_key")
        if val: return val
    except Exception as exc:
        print(f"[Gemini STT] Cannot read gemini_api_key from frappe.conf: {exc}")
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

def _clean_segment_text(text):
    """Normalize STT text without changing meeting meaning."""
    if not text:
        return ""

    cleaned = str(text).strip()
    replacements = {
        "Nhật trình": "Tờ trình",
        "nhật trình": "tờ trình",
        "Nhặt trình": "Tờ trình",
        "nhặt trình": "tờ trình",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)

    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)

    filler_only = re.compile(
        r"^\s*(?:dạ|vâng|ừ|ừm|ờ|à|okay|ok|được anh|dạ em hiểu rồi)[\s,.!?;:]*$",
        re.IGNORECASE,
    )
    if filler_only.fullmatch(cleaned):
        return ""

    filler_phrases = [
        "ừm", "ờ", "à", "thì là", "ý là", "tức là", "kiểu như",
        "vậy á", "nha anh", "đó nha", "nghen",
    ]
    for phrase in filler_phrases:
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)[\s,]*"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    prev = None
    repeated_word = re.compile(r"(?i)\b([\wÀ-ỹ]+)(?:\s+\1\b)+")
    while prev != cleaned:
        prev = cleaned
        cleaned = repeated_word.sub(r"\1", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned

def _convert_to_flac(wav_path, log_cb=None):
    """Nén wav sang FLAC (lossless, ~3 lần nhỏ hơn) chỉ để upload lên Gemini —
    giảm thời gian upload đáng kể với file dài, không đụng tới wav gốc (vẫn
    dùng cho VAD/cắt audio embedding ở chỗ khác). Trả về None nếu nén lỗi,
    khi đó gọi nơi dùng nên fallback lại upload thẳng wav gốc."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        flac_path = f.name
    try:
        result = subprocess.run(  # nosec B603
            ["ffmpeg", "-y", "-i", wav_path, "-c:a", "flac", flac_path],
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0:
            with suppress(FileNotFoundError):
                os.remove(flac_path)
            _parse_log(f"[Gemini STT] Nén FLAC lỗi, dùng wav gốc: {result.stderr[-300:]}", log_cb)
            return None
        return flac_path
    except Exception as e:
        with suppress(FileNotFoundError):
            os.remove(flac_path)
        _parse_log(f"[Gemini STT] Nén FLAC lỗi ({e}), dùng wav gốc.", log_cb)
        return None


def _upload_file_data(wav_path, api_key, log_cb=None, mime_type="audio/wav"):
    """Upload file lên Gemini, trả về (file_uri, file_name) ngay khi upload xong (chưa chờ ACTIVE)."""
    session = _get_session()
    file_size = os.path.getsize(wav_path)

    query, auth_headers = _get_auth_headers_and_query(api_key)

    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
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
                delay = _retry_delay(attempt)
                _parse_log(f"[Gemini STT] 429 upload init, thử lại {attempt + 1}/{_RETRY_MAX - 1} sau {delay:.1f}s...", log_cb)
                time.sleep(delay)
                continue
            init.raise_for_status()
            break
        except (_requests.exceptions.RequestException, IOError) as e:
            if attempt < _RETRY_MAX - 1:
                delay = _retry_delay(attempt)
                _parse_log(f"[Gemini STT] Lỗi kết nối (init upload) ({type(e).__name__}), thử lại sau {delay:.1f}s...", log_cb)
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
                delay = _retry_delay(attempt)
                _parse_log(f"[Gemini STT] 429 upload data, thử lại {attempt + 1}/{_RETRY_MAX - 1} sau {delay:.1f}s...", log_cb)
                time.sleep(delay)
                continue
            upload_resp.raise_for_status()
            break
        except (_requests.exceptions.RequestException, IOError) as e:
            if attempt < _RETRY_MAX - 1:
                delay = _retry_delay(attempt)
                _parse_log(f"[Gemini STT] Lỗi kết nối (upload data) ({type(e).__name__}), thử lại sau {delay:.1f}s...", log_cb)
                time.sleep(delay)
                continue
            raise

    file_info = upload_resp.json()["file"]
    file_uri  = file_info["uri"]
    file_name = file_info["name"]
    _parse_log(f"[Gemini STT] Uploaded → {file_uri}, chờ ACTIVE...", log_cb)
    return file_uri, file_name


def _wait_file_active(file_name, file_uri, api_key, log_cb=None):
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
            _parse_log(f"[Gemini STT] File status {sr.status_code}, retrying...", log_cb)
            time.sleep(_retry_delay(0, 0, 2))
            continue
        sr.raise_for_status()
        state = sr.json().get("state", "")
        if state == "ACTIVE":
            _parse_log(f"[Gemini STT] File ACTIVE: {file_uri}", log_cb)
            return
        if state == "FAILED":
            raise Exception(f"Gemini file processing FAILED: {file_name}")
        time.sleep(5)
    raise Exception("Gemini file processing timeout sau 200s")


def _upload_file(wav_path, api_key, log_cb=None, mime_type="audio/wav"):
    """Upload và chờ ACTIVE (wrapper để tương thích ngược)."""
    file_uri, file_name = _upload_file_data(wav_path, api_key, log_cb=log_cb, mime_type=mime_type)
    _wait_file_active(file_name, file_uri, api_key, log_cb=log_cb)
    return file_uri, file_name


def _delete_file(file_name, api_key, log_cb=None):
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
            _parse_log(f"[Gemini STT] Deleted: {file_name}", log_cb)
        else:
            _parse_log(f"[Gemini STT] Delete failed {resp.status_code}: {file_name}", log_cb)
    except Exception as e:
        _parse_log(f"[Gemini STT] Delete error: {e}", log_cb)


def _call_gemini_stream(file_uri, api_key, prompt, model_name=None, max_tokens=12000, log_cb=None, mime_type="audio/wav"):
    """Gọi Gemini stream API, trả về (segments, usage_dict, error_str|None)."""
    session = _get_session()
    if not model_name:
        model_name = _get_gemini_model()

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                {"text": prompt},
            ]
        }],
        "generation_config": {
            "temperature": 0.3,
            # text/plain thay vì application/json: không còn ép model phải giữ
            # 1 array JSON hợp lệ xuyên suốt hàng trăm object lặp cấu trúc —
            # đây là dạng output tự nhiên giống AI Studio, ít bị cuốn vào vòng
            # lặp cấu trúc hơn. speaker/text/start/end mỗi dòng dạng text
            # thường, không phải JSON, nên không có áp lực cấu trúc lặp.
            "response_mime_type": "text/plain",
            "maxOutputTokens": max_tokens,
            # Tắt suy luận ẩn. Model đời này mặc định "nghĩ" trước khi trả lời,
            # mà phần nghĩ đó tính vào chính hạn mức maxOutputTokens — nghe lại
            # audio thì không cần suy luận, nên nó chỉ ăn chỗ của transcript.
            # Đo thật trên một clip: 831 token nghĩ so với 150 token chữ, tức
            # gần nửa hạn mức đổ vào phần không thành chữ; tắt đi thì vẫn ra
            # đúng ngần ấy chữ (134 so với 135 từ). Trên file 80 phút, chính
            # phần nghĩ này đốt hết 64k token rồi bị cắt giữa chừng, làm mất
            # ba phần tư nội dung.
            "thinkingConfig": {"thinkingBudget": 0},
            # KHÔNG dùng presencePenalty/frequencyPenalty — test thật với
            # model hiện tại (gemini-3.5-flash) trả lỗi 400 "Penalty is not
            # enabled for this model". Chống lặp giờ dựa vào prompt (nguyên
            # tắc ANTI-LOOP) + text/plain output, không phải generation_config.
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
        _parse_log(f"[Gemini STT] Streaming attempt {attempt + 1}/{_RETRY_MAX} (model={model_name})...", log_cb)
        try:
            resp = session.post(url, json=payload, headers=auth_headers, timeout=1800, stream=True)

            if resp.status_code in [403, 429, 500, 502, 503, 504]:
                if attempt < _RETRY_MAX - 1:
                    delay = _retry_delay(attempt)
                    _parse_log(f"[Gemini STT] {resp.status_code} stream, thử lại sau {delay:.1f}s...", log_cb)
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
                delay = _retry_delay(attempt)
                _parse_log(f"[Gemini STT] Connection error ({type(e).__name__}), thử lại sau {delay:.1f}s...", log_cb)
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
    usage_result["cost_usd"] = cost
    usage_result["input_cost_usd"] = total_in * PRICE_IN
    usage_result["output_cost_usd"] = billable_out * PRICE_OUT
    _parse_log(
        f"💰 [Gemini STT] model={model_name} | "
        f"in={total_in:,} out={billable_out:,} (think={thoughts_tokens}) | "
        f"total={total_tokens:,} tokens | cost=~${cost:.4f} USD | finish={finish_reason}"
        ,
        log_cb,
    )

    if finish_reason == "MAX_TOKENS":
        _parse_log("[Gemini STT] ⚠️ MAX_TOKENS — Phát hiện vòng lặp ảo giác.", log_cb)
        return _parse_gemini_response(full_text), usage_result, "HALLUCINATION_DETECTED"
    elif finish_reason == "SAFETY":
        return [], usage_result, "Safety filter rejected content"

    if not full_text:
        return [], usage_result, f"Gemini không trả về text (finish={finish_reason})"

    return _parse_gemini_response(full_text), usage_result, None


def _build_prompt(num_speakers, language, custom_vocabulary=""):
    lang_note    = "tiếng Việt" if language in ("vi", "vi-VN") else language
    speaker_note = (
        f"Cuộc họp có KHOẢNG {num_speakers} người tham dự. Đây chỉ là gợi ý ban đầu, KHÔNG phải giới hạn cứng. Nếu nghe thấy nhiều giọng hơn, hãy tạo thêm Speaker mới."
        if num_speakers else
        "Cuộc họp có thể có nhiều người tham dự."
    )
    custom_vocab_note = f"\n{custom_vocabulary}" if custom_vocabulary else ""

    return f"""Bạn là chuyên gia phiên âm và biên tập biên bản họp. Nhiệm vụ: xử lý file ghi âm cuộc họp nội bộ bằng {lang_note} và trả ra transcript đã được làm sạch hoàn toàn.

━━━ BƯỚC 1: NHẬN DẠNG GIỌNG NÓI & TÁCH NGƯỜI NÓI (DIARIZATION) ━━━
- Transcribe TOÀN BỘ nội dung từ đầu đến cuối file, ĐÚNG THEO THỨ TỰ THỜI GIAN THỰC TẾ — KHÔNG được bỏ sót bất kỳ lượt nói nào, KHÔNG được đảo thứ tự các lượt nói.
- LƯU Ý SỐ LƯỢNG NGƯỜI NÓI: {speaker_note}
- KHÔNG ĐƯỢC TỰ BỊA ĐẶT LỜI THOẠI. Chỉ ghi chép những gì nghe được.
- ĐÂY LÀ YÊU CẦU QUAN TRỌNG NHẤT: BẠN PHẢI PHÂN BIỆT ĐƯỢC CÁC GIỌNG NÓI KHÁC NHAU. MỖI LƯỢT ĐỔI NGƯỜI NÓI (dù chỉ là tiếng xen ngang "Đúng rồi", "Ok") = 1 DÒNG RIÊNG BIỆT.
- CHÚ Ý ĐẶC BIỆT: Tuyệt đối KHÔNG ĐƯỢC BỎ SÓT các từ ở ngay ĐẦU và CUỐI file âm thanh. Hãy lắng nghe thật kỹ ngay từ giây đầu tiên.
- NẾU CÓ 2 NGƯỜI NÓI ĐÈ LÊN NHAU (OVERLAP) HOẶC CÃI NHAU: TUYỆT ĐỐI KHÔNG GỘP CHUNG CHỮ VÀO 1 DÒNG. Bắt buộc phải tách lời của người A và người B thành 2 dòng nối tiếp nhau. LỖI NGHIÊM TRỌNG NHẤT LÀ NHÉT LỜI CỦA 2 NGƯỜI VÀO CÙNG 1 CÂU NÓI CỦA 1 NGƯỜI.
- CÂU HỎI và CÂU TRẢ LỜI luôn là 2 dòng riêng biệt — người hỏi và người trả lời KHÔNG bao giờ được gộp chung.
- Nếu một đoạn có nhiều người nói liên tục, HÃY CẮT NHỎ THÀNH NHIỀU DÒNG LIÊN TIẾP.
- TUYỆT ĐỐI KHÔNG TRẢ VỀ 1 DÒNG KÉO DÀI NHIỀU PHÚT. Nếu một người nói liên tục quá lâu, BẮT BUỘC PHẢI CẮT NHỎ lời nói của họ thành nhiều dòng liên tiếp (mỗi dòng khoảng 3-5 câu).
- Hãy đối chiếu ÂM THANH THỰC TẾ: cao độ giọng, tốc độ nói, chất giọng. Nếu trong một đoạn liên tục có sự thay đổi âm sắc (ví dụ từ giọng nam trầm sang giọng nam cao, hoặc giọng nữ) → PHẢI TẠO DÒNG MỚI NGAY TẠI ĐIỂM ĐÓ.
- KHÔNG suy đoán speaker theo ngữ cảnh (ai đặt câu hỏi thì ai trả lời) — CHỈ ĐƯỢC PHÉP dựa vào sự thay đổi thực tế của sóng âm/chất giọng mà bạn nghe được.
- Bỏ qua tạp âm, tiếng ồn, tiếng động nền.
- CỰC KỲ QUAN TRỌNG: Nếu đoạn âm thanh LÀ KHOẢNG LẶNG, CHỈ CÓ TẠP ÂM, HOẶC KHÔNG CÓ TIẾNG NGƯỜI NÓI, TUYỆT ĐỐI KHÔNG ĐƯỢC TỰ BỊA RA LỜI NÓI HOẶC LẶP LẠI LỜI CŨ. HÃY TRẢ VỀ RỖNG (không viết dòng nào) NẾU KHÔNG NGHE THẤY GÌ.
- NGUYÊN TẮC CHỐNG LẶP (ANTI-LOOP): Khi đã transcribe hết tiếng người nói thực sự trong audio, BẠN PHẢI DỪNG LẠI NGAY LẬP TỨC, không viết thêm dòng nào nữa. TUYỆT ĐỐI KHÔNG được lặp lại một câu nói nhiều lần. Nếu bạn thấy mình chuẩn bị viết lại cùng một câu (hoặc một cụm từ) đến lần thứ 2 liên tiếp mà không có tiếng nói thực sự tương ứng, hãy LẬP TỨC DỪNG LẠI.

━━━ BƯỚC 2: LÀM SẠCH VĂN BẢN ━━━
Chỉ xoá các từ/âm KHÔNG mang thông tin BÊN TRONG câu, KHÔNG được xoá cả dòng:
- Xoá từ đệm/ngập ngừng: "ừm", "ờ", "à", "thì là", "ý là", "tức là", "kiểu như", "vậy á", "nha anh", "đó nha", "nghen"
- Xoá lặp từ do ngập ngừng: "cái cái cái" → bỏ, "nó nó nó" → "nó", "các ảnh các ảnh" → "các ảnh", v.v.
- Xoá câu chỉ là filler/xác nhận không có thông tin: "dạ", "vâng", "okay", "ừ", "dạ em hiểu rồi", "được anh"
- Viết lại thành câu hoàn chỉnh, dấu câu chuẩn, viết hoa đầu câu
- TUYỆT ĐỐI GIỮ ĐÚNG NGHĨA GỐC — không thêm, không bịa, không suy diễn, không tóm tắt
- Giữ code-switching Việt-Anh (không dịch thuật ngữ tiếng Anh)

━━━ TỪ VỰNG ĐẶC BIỆT (nhận dạng chính xác) ━━━{custom_vocab_note}

━━━ OUTPUT FORMAT ━━━
Trả về TEXT THUẦN (PLAIN TEXT) — KHÔNG dùng JSON, KHÔNG markdown, KHÔNG code block, KHÔNG giải thích gì thêm ngoài transcript. KHÔNG cần tính timestamp/giây — hệ thống sẽ tự gán thời gian dựa trên audio thật, bạn CHỈ cần tập trung nghe đúng và tách đúng người nói theo thứ tự.
Mỗi lượt nói là MỘT DÒNG riêng biệt, đúng định dạng "Speaker <số>: <nội dung>", ví dụ:
Speaker 1: nội dung đã làm sạch
Speaker 2: nội dung đã làm sạch
RÀNG BUỘC BẮT BUỘC VỚI MỖI DÒNG:
- Mỗi dòng chỉ được chứa lời của ĐÚNG 1 người nói trong đúng 1 lượt nói.
- Nếu trong cùng một khoảng thời gian nghe thấy 2 người, hoặc nội dung có dạng "A nói... B đáp...", phải tách thành 2 dòng riêng.
- Không được viết một dòng mà bên trong có lời của 2 speaker khác nhau, kể cả khi họ nói rất ngắn, chen ngang, xác nhận, hỏi/đáp nhanh hoặc nói đè.
- Trước khi trả lời, tự kiểm tra từng dòng: nếu nội dung còn chứa lời đối thoại của hơn 1 người thì bắt buộc tách dòng đó ra.
- KHÔNG dùng dấu ngoặc kép hay markdown bao quanh dòng.
- Các dòng PHẢI theo ĐÚNG thứ tự thời gian thực tế của cuộc hội thoại, từ đầu đến cuối file."""


_SPEAKER_LINE_RE = re.compile(r'^\s*(Speaker\s*\d+)\s*[:：]\s*(.+?)\s*$', re.IGNORECASE)


def _parse_gemini_response(text):
    """Parse text thuần dạng 'Speaker N: nội dung' mỗi dòng → list segment.

    Không còn parse JSON: mỗi dòng độc lập nên bị cắt giữa chừng (MAX_TOKENS)
    cũng không làm hỏng các dòng trước đó, khỏi cần logic "cứu" JSON dở dang.
    """
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()

    segments = []
    skipped = 0
    for raw_line in text.splitlines():
        # Bỏ markdown (**, •, gạch đầu dòng) phòng khi model lỡ thêm dù prompt đã cấm.
        line = raw_line.strip().strip('"').replace("*", "").replace("•", "")
        line = re.sub(r"^-\s*", "", line).strip()
        if not line:
            continue
        match = _SPEAKER_LINE_RE.match(line)
        if not match:
            skipped += 1
            continue
        speaker = re.sub(r"\s+", " ", match.group(1)).strip()
        content = match.group(2).strip()
        if not content:
            continue
        segments.append({"speaker": speaker, "text": content})

    if skipped:
        print(f"[Gemini STT] Bỏ qua {skipped} dòng không đúng định dạng 'Speaker N: ...'.")
    return segments


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


def _timeline_validation_errors(segments, file_duration, check_long_segments=True):
    """Return reasons a Gemini timeline is unsafe for cutting speaker audio."""
    duration = max(0.0, float(file_duration or 0.0))
    parsed = []
    errors = []

    for index, seg in enumerate(segments or []):
        if not isinstance(seg, dict):
            continue
        start = _parse_time(seg.get("start", 0))
        end = _parse_time(seg.get("end", start))
        text = " ".join(str(seg.get("text") or "").split())
        words = text.split()
        seg_duration = end - start
        parsed.append((index, start, end, seg_duration, len(words), text))

        if start < -0.25 or end > duration + 1.0:
            errors.append(f"segment {index} nằm ngoài chunk ({start:.2f}-{end:.2f}/{duration:.2f}s)")
        if words and seg_duration <= 0:
            errors.append(f"segment {index} có text nhưng start>=end ({start:.2f}-{end:.2f})")

        # Prompt yêu cầu mỗi entry chỉ vài câu. Một entry chiếm quá nhiều
        # thời gian thường là Gemini tự phân bổ timestamp theo lượng text.
        long_limit = max(45.0, duration * 0.22)
        if check_long_segments and words and seg_duration > long_limit:
            errors.append(f"segment {index} dài bất thường {seg_duration:.2f}s")

        # Dưới 0.45 từ/giây trong một segment đủ dài là dấu hiệu mốc thời
        # gian bị kéo giãn, không phải tốc độ nói thực tế.
        if (
            check_long_segments
            and len(words) >= 8
            and seg_duration >= 15.0
            and (len(words) / seg_duration) < 0.45
        ):
            errors.append(
                f"segment {index} bị kéo giãn ({len(words)} từ/{seg_duration:.2f}s)"
            )

    if not parsed:
        return ["chunk không có segment hợp lệ"]

    # Gemini đôi lúc dồn nhiều entry vào đúng mép cuối, thậm chí tạo entry
    # start=end nhưng vẫn chứa một đoạn văn dài.
    near_tail = [row for row in parsed if duration > 0 and row[2] >= duration - 0.15]
    if len(near_tail) >= 2:
        errors.append(f"{len(near_tail)} segment bị dồn vào cuối chunk")
    last = parsed[-1]
    if duration > 0 and last[2] >= duration - 0.15 and last[3] <= 0.15 and last[4] >= 5:
        errors.append("segment cuối có text dài nhưng thời lượng gần bằng 0")

    return list(dict.fromkeys(errors))


def _vad_speech_intervals(wav_path):
    """Return merged speech intervals using local VAD only."""
    import wave

    import webrtcvad

    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        frame_count = wav_file.getnframes()
        data = wav_file.readframes(frame_count)

    duration = frame_count / sample_rate if sample_rate else 0.0
    if channels != 1 or sample_rate not in (8000, 16000, 32000, 48000):
        return [(0.0, duration)] if duration > 0 else []

    frame_ms = 30
    frame_samples = int(sample_rate * frame_ms / 1000)
    frame_bytes = frame_samples * sample_width
    vad = webrtcvad.Vad(1)
    raw_intervals = []
    speech_start = None

    for byte_offset in range(0, len(data) - frame_bytes + 1, frame_bytes):
        frame_index = byte_offset // frame_bytes
        start = frame_index * frame_ms / 1000.0
        is_speech = vad.is_speech(data[byte_offset : byte_offset + frame_bytes], sample_rate)
        if is_speech and speech_start is None:
            speech_start = start
        elif not is_speech and speech_start is not None:
            raw_intervals.append((speech_start, start))
            speech_start = None
    if speech_start is not None:
        raw_intervals.append((speech_start, duration))

    if not raw_intervals:
        return [(0.0, duration)] if duration > 0 else []

    merged = []
    for start, end in raw_intervals:
        if merged and start - merged[-1][1] <= 0.3:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _speech_clock_to_audio_time(intervals, speech_seconds):
    remaining = max(0.0, float(speech_seconds or 0.0))
    for start, end in intervals:
        interval_duration = max(0.0, end - start)
        if remaining <= interval_duration:
            return start + remaining
        remaining -= interval_duration
    return intervals[-1][1] if intervals else 0.0


_VAD_TURN_GAP_SEC = 0.15  # đệm giả lập giữa 2 lượt nói khác speaker


def _retime_segments_by_vad(segments, wav_path):
    """Dựng start/end cho các segment đã có sẵn thứ tự, bằng cách rải text lên
    các vùng VAD báo là có tiếng nói.

    Mốc ở đây là ước lượng, không phải đo từng chữ: nó giữ đúng thứ tự và nằm
    trong vùng có tiếng, đủ cho việc hiển thị. Khâu nhận diện người nói không
    dùng tới mốc này — nó gom cụm giọng riêng — nên sai lệch ở đây không kéo
    theo gán nhầm người."""
    segments = [dict(seg) for seg in (segments or []) if isinstance(seg, dict)]
    if not segments:
        return []

    intervals = _vad_speech_intervals(wav_path)
    total_speech = sum(max(0.0, end - start) for start, end in intervals)
    if total_speech <= 0:
        return segments

    weights = [max(1, len(_normalized_text_tokens(seg.get("text")))) for seg in segments]
    total_weight = max(1, sum(weights))
    consumed_weight = 0

    for idx, (seg, weight) in enumerate(zip(segments, weights)):
        start_clock = total_speech * consumed_weight / total_weight
        consumed_weight += weight
        end_clock = total_speech * consumed_weight / total_weight

        # Phân bổ toán học thuần tuý luôn cho end_clock == start_clock của lượt
        # kế tiếp (gap=0 tuyệt đối), dù người thật luôn có khoảng ngừng dù nhỏ
        # khi đổi người nói. Bớt lại 1 chút cuối lượt khi SẮP đổi speaker, để
        # tránh cắt clip embedding dính giọng người nói kế tiếp.
        next_seg = segments[idx + 1] if idx + 1 < len(segments) else None
        if next_seg is not None and next_seg.get("speaker") != seg.get("speaker"):
            end_clock = max(start_clock, end_clock - _VAD_TURN_GAP_SEC)

        seg["start"] = round(_speech_clock_to_audio_time(intervals, start_clock), 2)
        seg["end"] = round(_speech_clock_to_audio_time(intervals, end_clock), 2)

    return segments


def _normalized_text_tokens(text):
    value = re.sub(r"[^\w\s]", " ", str(text or "").casefold(), flags=re.UNICODE)
    return [token for token in value.split() if token]


def _segments_to_raw_words(segments, file_duration=None, log_cb=None):
    """Convert Gemini segments → raw_words format tương thích pipeline."""
    segments = [s for s in segments if isinstance(s, dict)]
    if not segments:
        return []

    raw_start = segments[0].get("start")
    raw_end   = segments[-1].get("end")
    _parse_log(f"[Gemini STT] Raw timestamps sample — first.start={raw_start!r} last.end={raw_end!r}", log_cb)

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
                    custom_vocabulary: str = "", progress_callback=None, existing_segments=None, parse_log_cb=None):
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
        try:
            import frappe
            frappe.log_error(f"Bat dau call_gemini_stt voi {len(chunks_info)} chunks, model={model_name}", "Gemini STT Debug")
        except Exception as exc:
            print(f"[Gemini STT] Debug log failed: {exc}")
        
        print(f"[Gemini STT] Xử lý {len(chunks_info)} chunks, lang={language}, speakers={num_speakers}")
        if parse_log_cb:
            with suppress(Exception):
                parse_log_cb("", f"[Gemini STT] Xử lý {len(chunks_info)} chunks, lang={language}, speakers={num_speakers}")
        prompt = _build_prompt(num_speakers, language, custom_vocabulary)
        max_output_tokens = get_gemini_stt_max_output_tokens()
        if parse_log_cb:
            with suppress(Exception):
                parse_log_cb("", f"[Gemini STT] maxOutputTokens/chunk={max_output_tokens}")

        chunks = chunks_info
        if progress_callback:
            progress_callback(20, f"Đang xử lý song song {len(chunks_info)} đoạn âm thanh...")

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
                    except (ValueError, TypeError, IndexError):
                        continue

        import threading
        _upload_lock = threading.Semaphore(8)

        def _process_single_chunk(chunk_dict):
            idx = chunk_dict.get("idx", 0)
            chunk_display = idx + 1 if isinstance(idx, int) else idx
            original_chunk_wav = chunk_dict.get("wav")
            current_wav = original_chunk_wav
            offset = chunk_dict.get("offset", 0.0)
            mappings = chunk_dict.get("mappings", [])
            chunk_name = chunk_dict.get("name", f"CHUNK_{idx}")
            parse_logs = []

            def append_chunk_log(message):
                parse_logs.append(message)

            def chunk_log(message):
                print(message)
                parse_logs.append(message)

            try:
                if idx in completed_chunks:
                    chunk_log(f"[Gemini STT] Bỏ qua chunk {idx+1}/{len(chunks_info)} vì đã hoàn thành.")
                    return idx, None, None, None, None, None, parse_logs

                chunk_log(f"[Gemini STT] Bắt đầu chunk {idx+1}/{len(chunks_info)} - offset: {offset:.1f}s")

                chunk_duration = get_duration(current_wav)

                # Nén sang FLAC trước khi upload — file dài thì wav gốc rất
                # nặng, FLAC lossless nhỏ hơn ~3 lần nên upload nhanh hơn hẳn
                # mà không ảnh hưởng độ chính xác phiên âm.
                flac_path = _convert_to_flac(current_wav, log_cb=append_chunk_log)
                upload_path = flac_path or current_wav
                upload_mime = "audio/flac" if flac_path else "audio/wav"

                # Upload với Semaphore 4
                try:
                    with _upload_lock:
                        file_uri, file_name = _upload_file(
                            upload_path, api_key, log_cb=append_chunk_log, mime_type=upload_mime
                        )
                finally:
                    if flac_path:
                        with suppress(FileNotFoundError):
                            os.remove(flac_path)

                chunk_error = None
                try:
                    gemini_segments, chunk_usage, chunk_error = _call_gemini_stream(
                        file_uri, api_key, prompt, model_name, max_tokens=max_output_tokens,
                        log_cb=append_chunk_log, mime_type=upload_mime,
                    )
                    if chunk_error and chunk_error != "HALLUCINATION_DETECTED":
                        chunk_log(f"[Gemini STT] Error on chunk {chunk_display}: {chunk_error}")
                finally:
                    # Luôn xóa remote file sau khi xong
                    _delete_file(file_name, api_key, log_cb=append_chunk_log)
                    if current_wav != original_chunk_wav:
                        with suppress(FileNotFoundError):
                            os.remove(current_wav)
                        # Do NOT remove original_chunk_wav, handled by api.py Voice Meeting Chunk records

                if not gemini_segments:
                    return idx, [], [], "", chunk_usage, None, parse_logs

                clean_segments = []
                for seg in gemini_segments:
                    if not isinstance(seg, dict): continue
                    text = seg.get("text", "").strip()
                    if not text: continue
                    text = _clean_segment_text(text)
                    if not text: continue
                    seg["text"] = text
                    clean_segments.append(seg)

                if not clean_segments:
                    return idx, [], [], "", chunk_usage, None, parse_logs

                # Gemini không còn trả start/end (bỏ khỏi prompt để giảm áp lực
                # lặp — thử thêm lại timestamp text thuần từng gây MAX_TOKENS
                # hallucination lại, đã rollback), nên phải tự dựng timeline.
                #
                # Trước đây dựng bằng forced-align service. Bỏ vì hai lẽ: mốc
                # nó trả về lệch tới hàng trăm giây trên file dài (CTC bị ép
                # nhồi chữ cho kín cửa sổ audio nó thấy), mà giờ cũng không còn
                # ai cần mốc chính xác — việc nhận diện người nói đã chuyển hẳn
                # sang gom cụm giọng theo VAD, không đụng tới timestamp. Còn
                # start/end ở đây chỉ để giữ thứ tự và cho các chỗ đọc field
                # này khỏi vỡ; VAD làm việc đó tại chỗ, không cần service ngoài
                # và không tốn vài phút mỗi file.
                clean_segments = _retime_segments_by_vad(clean_segments, current_wav)
                raw_words = _segments_to_raw_words(clean_segments, log_cb=append_chunk_log)

                timeline_errors = _timeline_validation_errors(
                    clean_segments,
                    chunk_duration,
                    check_long_segments=True,
                )

                # Hàm map thời gian đặc ruột về thời gian gốc
                def map_time(t_val):
                    t = _parse_time(t_val)
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

                if timeline_errors:
                    detail = "; ".join(timeline_errors[:6])
                    chunk_log(f"[Gemini STT] Chunk {idx + 1} timeline cảnh báo (không chặn kết quả): {detail}")

                return idx, segments, raw_words, chunk_text, chunk_usage, None, parse_logs

            except Exception as e:
                import traceback
                traceback.print_exc()
                chunk_log(f"[Gemini STT] Exception chunk {chunk_display}: {e}")
                return idx, None, None, None, None, str(e), parse_logs

        # Chạy tất cả chunk song song
        try:
            frappe.log_error(f"Bat dau chay ThreadPoolExecutor cho {len(chunks)} chunks", "Gemini STT Debug")
        except Exception as exc:
            print(f"[Gemini STT] Debug log failed: {exc}")
        
        if chunk_update_cb:
            for c in chunks:
                with suppress(Exception):
                    chunk_update_cb(c.get("name", ""), "Processing", None, None, None, 0)
        
        completed_count = 0
        total_chunks    = len(chunks)
        results         = {}
        total_in_all    = 0
        total_out_all   = 0
        total_tok_all   = 0
        chunk_errors    = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(chunks), 6)) as executor:
            future_to_chunk = {
                executor.submit(_process_single_chunk, chunk_dict): chunk_dict
                for chunk_dict in chunks
            }

            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_dict = future_to_chunk[future]
                idx = chunk_dict.get("idx", 0)
                c_name = chunk_dict.get("name", "")
                try:
                    res_idx, segments, raw_words, chunk_text, chunk_usage, err_msg, parse_logs = future.result()
                    if err_msg:
                        chunk_errors.append(f"Chunk {idx+1}: {err_msg}")
                        if chunk_update_cb:
                            with suppress(Exception):
                                chunk_update_cb(c_name, "Error", None, None, err_msg, 0, parse_logs)
                    else:
                        results[res_idx] = (segments, raw_words, chunk_text)
                        if chunk_update_cb:
                            with suppress(Exception):
                                chunk_update_cb(
                                    c_name,
                                    "Completed",
                                    segments,
                                    raw_words,
                                    None,
                                    chunk_usage.get("tokens_used", 0) if chunk_usage else 0,
                                    parse_logs,
                                    chunk_usage,
                                )

                    if chunk_usage:
                        total_in_all  += chunk_usage.get("prompt_tokens", 0)
                        total_out_all += chunk_usage.get("completion_tokens", 0)
                        total_tok_all += chunk_usage.get("tokens_used", 0)
                except Exception as e:
                    import traceback
                    err_trace = traceback.format_exc()
                    with suppress(Exception):
                        frappe.log_error(f"Loi tai chunk future result: {err_trace}", "Gemini STT Debug")
                    chunk_errors.append(f"Chunk {idx+1}: {str(e)}")
                    if chunk_update_cb:
                        with suppress(Exception):
                            chunk_update_cb(c_name, "Error", None, None, str(e), 0, [str(e)])

                completed_count += 1
                if progress_callback:
                    pct = int((completed_count / total_chunks) * 100)
                    progress_callback(pct, f"Đang xử lý: xong {completed_count}/{total_chunks} đoạn...")

        sorted_results = [results[k] for k in sorted(results.keys())]
        for res in sorted_results:
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
                    except (ValueError, TypeError, IndexError):
                        continue

        all_segments.sort(key=lambda x: x.get('start', 0))

        if chunk_errors:
            error_details = " | ".join(chunk_errors)
            return all_segments, all_raw_words, all_full_text.strip(), \
                   f"Lỗi xử lý file (Gemini): {error_details}", total_in_all, total_out_all

        if not all_segments:
            return [], [], "", "Gemini không nhận ra giọng nói trong file (file trống, nhiễu hoặc sai format).", 0, 0

        spk_set = set()
        for s in all_segments:
            s_spk = s.get("speaker_id", "")
            if s_spk and s_spk not in spk_set:
                spk_set.add(s_spk)
        n_spk = len(spk_set)
        
        PRICE_IN  = 1.50 / 1_000_000
        PRICE_OUT = 9.00 / 1_000_000
        total_cost = total_in_all * PRICE_IN + total_out_all * PRICE_OUT
        total_log = (
            f"[Gemini STT] ✅ DONE: {len(all_segments)} segments, {n_spk} speakers, {len(chunks_info)} chunks\n"
            f"💰 [Gemini STT] TỔNG CHI PHÍ FILE: "
            f"in={total_in_all:,} + out={total_out_all:,} = {total_tok_all:,} tokens | "
            f"cost=~${total_cost:.4f} USD ({len(chunks_info)} chunks)"
        )
        print(total_log)
        if parse_log_cb:
            with suppress(Exception):
                parse_log_cb("", total_log)
        with suppress(Exception):
            frappe.log_error(f"call_gemini_stt hoan thanh. Segments: {len(all_segments)}, Loi: {chunk_errors}", "Gemini STT Debug")
        
        return all_segments, all_raw_words, all_full_text.strip(), None, total_in_all, total_out_all

    except Exception as e:
        import traceback
        traceback.print_exc()
        return [], [], "", f"Lỗi Gemini STT: {e}", 0, 0
