import os
import time
import json
import re
import requests as _requests
from .audio_utils import get_duration

UPLOAD_URL      = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GENERATE_URL    = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FILE_STATUS_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"

def _get_gemini_model():
    try:
        import frappe
        val = frappe.conf.get("gemini_model")
        if val: return val
    except Exception: pass
    return os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

def _get_api_key():
    try:
        import frappe
        val = frappe.conf.get("gemini_api_key")
        if val: return val
    except Exception: pass
    return os.getenv("GEMINI_API_KEY", "")

def _upload_file(wav_path, api_key):
    """Upload audio lên Gemini File API, chờ ACTIVE rồi trả về file URI."""
    file_size = os.path.getsize(wav_path)
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": "audio/wav",
        "Content-Type": "application/json",
    }
    init = _requests.post(
        f"{UPLOAD_URL}?key={api_key}",
        headers=headers,
        json={"file": {"display_name": os.path.basename(wav_path)}},
        timeout=30,
    )
    init.raise_for_status()
    upload_url = init.headers["X-Goog-Upload-URL"]

    with open(wav_path, "rb") as f:
        data = f.read()
    upload_resp = _requests.post(
        upload_url,
        headers={
            "Content-Length": str(file_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        data=data,
        timeout=300,
    )
    upload_resp.raise_for_status()
    file_info = upload_resp.json()["file"]
    file_uri  = file_info["uri"]
    file_name = file_info["name"]
    print(f"[Gemini STT] Uploaded → {file_uri}, chờ ACTIVE...")

    for _ in range(30):
        status_resp = _requests.get(
            f"{FILE_STATUS_URL.format(name=file_name)}?key={api_key}",
            timeout=10,
        )
        status_resp.raise_for_status()
        state = status_resp.json().get("state", "")
        if state == "ACTIVE":
            print(f"[Gemini STT] File ACTIVE: {file_uri}")
            return file_uri
        if state == "FAILED":
            raise Exception(f"Gemini file processing FAILED: {file_name}")
        time.sleep(5)

    raise Exception("Gemini file processing timeout sau 150s")

STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"

def _call_gemini_stream(file_uri, api_key, prompt):
    """
    Gọi Gemini Streaming API (streamGenerateContent) — giống hệt Gemini Web.
    Không bị cắt ngang do MAX_TOKENS vì nhận token liên tục cho đến hết.
    Trả về danh sách segments đã parse.
    """
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
            "temperature": 0,
        },
    }

    print(f"[Gemini STT] Streaming (model={model_name})...")
    resp = _requests.post(
        f"{STREAM_URL.format(model=model_name)}?key={api_key}&alt=sse",
        json=payload,
        timeout=1200,
        stream=True,
    )
    resp.raise_for_status()

    full_text   = ""
    total_in    = 0
    total_out   = 0
    finish_reason = None

    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        usage = chunk.get("usageMetadata", {})
        if usage:
            total_in  = usage.get("promptTokenCount", total_in)
            total_out = usage.get("candidatesTokenCount", total_out)

        candidates = chunk.get("candidates", [])
        if not candidates:
            continue

        cand = candidates[0]
        finish_reason = cand.get("finishReason", finish_reason)

        parts = cand.get("content", {}).get("parts", [])
        for part in parts:
            if not part.get("thought", False) and "text" in part:
                full_text += part["text"]

    cost = (total_in * 1.25 + total_out * 5.0) / 1_000_000
    print(f"💰 [Gemini Stream] in={total_in} out={total_out} | ~${cost:.4f} | finish={finish_reason}")

    if finish_reason == "MAX_TOKENS":
        print("[Gemini STT] ⚠️ MAX_TOKENS — transcript bị cắt. Xem xét tăng output token limit.")
    elif finish_reason == "SAFETY":
        raise RuntimeError("Safety filter rejected content")

    if not full_text:
        raise RuntimeError(f"Gemini không trả về text (finish={finish_reason})")

    return _parse_gemini_response(full_text)


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
- Mỗi lượt đổi người nói = 1 entry JSON riêng. Tuyệt đối KHÔNG gộp lời của 2 người khác nhau vào cùng một entry.
- Phân biệt từng người nói dựa vào âm sắc giọng và phải nhất quán người đó từ đầu đến cuối.
- Câu hỏi ngắn, đáp lời ngắn, xen ngang đều phải có entry riêng — KHÔNG bỏ qua dù ngắn.
- CÂU HỎI và CÂU TRẢ LỜI luôn là 2 entry riêng biệt — người hỏi và người trả lời KHÔNG bao giờ được gộp chung.
- Trước khi gán speaker cho mỗi entry, hãy đối chiếu ÂM THANH THỰC TẾ: cao độ giọng, tốc độ nói, chất giọng. Nếu trong một đoạn liên tục có sự thay đổi âm sắc → phải tách entry mới ngay tại điểm đó.
- KHÔNG suy đoán speaker theo ngữ cảnh (ai đặt câu hỏi thì ai trả lời) — chỉ dựa vào giọng nói thực tế nghe được.
- Bỏ qua tạp âm, tiếng ồn, tiếng động nền.

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
]"""


def _parse_gemini_response(text):
    """Extract JSON array từ Gemini response."""
    text = re.sub(r"^```(?:json)?\s*|```\s*$", "", text.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    text_to_parse = match.group() if match else text

    try:
        return json.loads(text_to_parse)
    except json.JSONDecodeError as e:
        print(f"[Gemini STT] Lỗi JSON: {e}. Đang thử cứu phần đã có...")
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

def _segments_to_raw_words(segments):
    """Convert Gemini segments → raw_words format tương thích pipeline."""
    raw_words = []
    for seg in segments:
        words = seg.get("text", "").split()
        if not words:
            continue
        start = float(seg.get("start", 0))
        end   = float(seg.get("end", start + 1))
        step  = (end - start) / len(words) if len(words) > 1 else (end - start)
        spk   = seg.get("speaker", "Speaker 1").replace(" ", "_").lower()
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
        if cur is None or cur["speaker_id"] != w["speaker_id"]:
            if cur: segments.append(cur)
            cur = {"start": w["start"], "end": w["end"],
                   "speaker_id": w["speaker_id"], "text": w["text"]}
        else:
            cur["end"]   = w["end"]
            cur["text"] += " " + w["text"]
    if cur: segments.append(cur)
    return segments

def call_gemini_stt(wav_path: str, language: str = "vi", num_speakers: int = None, custom_vocabulary: str = ""):
    """
    Google Gemini STT với speaker diarization.
    Trả về: (segments, raw_words, full_text, error, 0, 0)
    """
    api_key = _get_api_key()
    if not api_key:
        return [], [], "", "Chưa cấu hình gemini_api_key trong site_config.json", 0, 0

    try:
        duration = get_duration(wav_path)
        print(f"[Gemini STT] File {duration:.1f}s, lang={language}, speakers={num_speakers}")
        prompt = _build_prompt(num_speakers, language, custom_vocabulary)

        file_uri        = _upload_file(wav_path, api_key)
        gemini_segments = _call_gemini_stream(file_uri, api_key, prompt)

        if not gemini_segments:
            return [], [], "", "Gemini không nhận ra giọng nói trong file.", 0, 0

        raw_words = _segments_to_raw_words(gemini_segments)
        segments  = _words_to_segments(raw_words)
        full_text = " ".join(s.get("text", "") for s in gemini_segments)
        n_spk     = len(set(s.get("speaker", "") for s in gemini_segments))
        print(f"[Gemini STT] OK: {len(segments)} segments, {n_spk} speakers")
        return segments, raw_words, full_text, None, 0, 0

    except Exception as e:
        return [], [], "", f"Lỗi Gemini STT: {e}", 0, 0
