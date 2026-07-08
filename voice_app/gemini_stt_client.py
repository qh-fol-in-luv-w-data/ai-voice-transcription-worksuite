import os
import time
import json
import re
import random
import asyncio
import aiohttp
from .audio_utils import get_duration
from .constants import get_gemini_api_key, get_gemini_model

UPLOAD_URL      = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GENERATE_URL    = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FILE_STATUS_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"
STREAM_URL      = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"

_RETRY_MAX        = 6
_RETRY_BASE_DELAY = 15

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

async def _upload_file(session: aiohttp.ClientSession, wav_path, api_key):
    file_size = os.path.getsize(wav_path)
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": "audio/wav",
        "Content-Type": "application/json",
    }

    for attempt in range(_RETRY_MAX):
        async with session.post(
            f"{UPLOAD_URL}?key={api_key}",
            headers=headers,
            json={"file": {"display_name": os.path.basename(wav_path)}},
            timeout=60,
        ) as init:
            if init.status == 429 and attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[Gemini STT] 429 upload init, thử lại {attempt + 1}/{_RETRY_MAX - 1} sau {delay}s...")
                await asyncio.sleep(delay)
                continue
            init.raise_for_status()
            upload_url = init.headers["X-Goog-Upload-URL"]
            break

    with open(wav_path, "rb") as f:
        data = f.read()
        
    async with session.post(
        upload_url,
        headers={
            "Content-Length": str(file_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        data=data,
        timeout=600,
    ) as upload_resp:
        upload_resp.raise_for_status()
        resp_json = await upload_resp.json()
        file_info = resp_json["file"]
        file_uri  = file_info["uri"]
        file_name = file_info["name"]
        
    print(f"[Gemini STT] Uploaded → {file_uri}, chờ ACTIVE...")

    for _ in range(30):
        async with session.get(
            f"{FILE_STATUS_URL.format(name=file_name)}?key={api_key}",
            timeout=30,
        ) as status_resp:
            if status_resp.status in [403, 429, 500, 502, 503, 504]:
                print(f"[Gemini STT] File status polling returned {status_resp.status}, retrying...")
                await asyncio.sleep(5)
                continue
            status_resp.raise_for_status()
            resp_json = await status_resp.json()
            state = resp_json.get("state", "")
            
            if state == "ACTIVE":
                print(f"[Gemini STT] File ACTIVE: {file_uri}")
                return file_uri, file_name
            if state == "FAILED":
                raise Exception(f"Gemini file processing FAILED: {file_name}")
            
        await asyncio.sleep(5)

    raise Exception("Gemini file processing timeout sau 200s")

async def _delete_file(session: aiohttp.ClientSession, file_name, api_key):
    try:
        async with session.delete(
            f"{FILE_STATUS_URL.format(name=file_name)}?key={api_key}",
            timeout=30,
        ) as resp:
            if resp.status in (200, 204):
                print(f"[Gemini STT] Deleted: {file_name}")
            else:
                print(f"[Gemini STT] Delete failed {resp.status}: {file_name}")
    except Exception as e:
        print(f"[Gemini STT] Delete error: {e}")

async def _call_gemini_stream(session: aiohttp.ClientSession, file_uri, api_key, prompt, model_name=None, max_tokens=12000):
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

    full_text     = ""
    total_in      = 0
    total_out     = 0
    finish_reason = None
    url = f"{STREAM_URL.format(model=model_name)}?key={api_key}&alt=sse"

    for attempt in range(_RETRY_MAX):
        print(f"[Gemini STT] Streaming attempt {attempt + 1}/{_RETRY_MAX} (model={model_name})...")
        try:
            async with session.post(
                url,
                json=payload,
                timeout=1800,
            ) as resp:
                if resp.status in [403, 429, 500, 502, 503, 504]:
                    if attempt < _RETRY_MAX - 1:
                        delay = _RETRY_BASE_DELAY * (2 ** attempt)
                        print(f"[Gemini STT] {resp.status} stream, thử lại sau {delay}s...")
                        await asyncio.sleep(delay)
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

                async for raw_line in resp.content:
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8").strip() if isinstance(raw_line, bytes) else raw_line.strip()
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        parsed_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    
                    chunks_to_process = parsed_data if isinstance(parsed_data, list) else [parsed_data]

                    for chunk in chunks_to_process:
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

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < _RETRY_MAX - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[Gemini STT] Connection error ({type(e).__name__}), thử lại sau {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise

    billable_out = max(total_tokens - total_in, total_out + thoughts_tokens)
    total_tokens = max(total_tokens, total_in + billable_out)
    usage_result = {
        "prompt_tokens": total_in,
        "completion_tokens": billable_out,
        "tokens_used": total_tokens,
        "candidate_tokens": total_out,
        "thoughts_tokens": thoughts_tokens,
        "cached_tokens": cached_tokens,
        "model": f"google/{model_name}",
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
- Mỗi lượt đổi người nói = 1 entry JSON riêng. Tuyệt đối KHÔNG gộp lời của 2 người khác nhau vào cùng một entry.
- Phân biệt từng người nói dựa vào âm sắc giọng và phải nhất quán người đó từ đầu đến cuối.
- Câu hỏi ngắn, đáp lời ngắn, xen ngang đều phải có entry riêng — KHÔNG bỏ qua dù ngắn.
- NẾU CÓ 2 NGƯỜI NÓI ĐÈ LÊN NHAU (cùng lúc) hoặc xen ngang: TUYỆT ĐỐI KHÔNG gộp lời của họ vào chung 1 câu. Phải tách riêng lời của người A và lời của người B ra 2 entry liên tiếp.
- CÂU HỎI và CÂU TRẢ LỜI luôn là 2 entry riêng biệt — người hỏi và người trả lời KHÔNG bao giờ được gộp chung.
- LỖI NGHIÊM TRỌNG NHẤT LÀ GỘP NHẦM LỜI CỦA 2 NGƯỜI THÀNH 1 CÂU. Nếu một đoạn có nhiều người nói liên tục, HÃY CẮT NHỎ THÀNH NHIỀU ENTRY.
- Trước khi gán speaker cho mỗi entry, hãy đối chiếu ÂM THANH THỰC TẾ: cao độ giọng, tốc độ nói, chất giọng. Nếu trong một đoạn liên tục có sự thay đổi âm sắc → phải tách entry mới ngay tại điểm đó.
- KHÔNG suy đoán speaker theo ngữ cảnh (ai đặt câu hỏi thì ai trả lời) — chỉ dựa vào giọng nói thực tế nghe được.
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
    # Đảm bảo tất cả segment là dict để tránh lỗi 'list'/'str' object has no attribute 'get'
    segments = [s for s in segments if isinstance(s, dict)]
    if not segments:
        return []

    raw_start = segments[0].get("start")
    raw_end   = segments[-1].get("end")
    print(f"[Gemini STT] Raw timestamps sample — first.start={raw_start!r} last.end={raw_end!r}")

    # Parse tất cả timestamps trước
    parsed = []
    for seg in segments:
        start = _parse_time(seg.get("start", 0))
        end   = _parse_time(seg.get("end", start + 1))
        parsed.append((start, end, seg))

    # Không áp dụng auto-detect phút/giây nữa vì Gemini 1.5 Flash trả về giây khá chuẩn, 
    # dùng heuristic rất dễ gây hỏng timestamp nếu người dùng chỉ nói một đoạn ngắn trong file dài.

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
        if cur is None or cur["speaker_id"] != w["speaker_id"]:
            if cur: segments.append(cur)
            cur = {"start": w["start"], "end": w["end"],
                   "speaker_id": w["speaker_id"], "text": w["text"]}
        else:
            cur["end"]   = w["end"]
            cur["text"] += " " + w["text"]
    if cur: segments.append(cur)
    return segments


def call_gemini_stt(wav_path: str, language: str = "vi", num_speakers: int = None, custom_vocabulary: str = "", progress_callback=None, existing_segments=None):
    try:
        # Sử dụng event loop mới để tránh lỗi "Event loop is already running" nếu có
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_async_call_gemini_stt(wav_path, language, num_speakers, custom_vocabulary, progress_callback, existing_segments))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return [], [], "", f"Lỗi Gemini STT: {e}", 0, 0
    finally:
        loop.close()

async def _async_call_gemini_stt(wav_path: str, language: str = "vi", num_speakers: int = None, custom_vocabulary: str = "", progress_callback=None, existing_segments=None):
    model_name = _get_gemini_model()
    empty_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tokens_used": 0,
        "model": f"google/{model_name}" if model_name else "google/gemini",
    }
    api_key = _get_api_key()
    if not api_key:
        return [], [], "", "Chưa cấu hình Gemini API Key trong Voice App Settings", 0, 0
    if not model_name:
        return [], [], "", "Chưa cấu hình Gemini Model trong Voice App Settings", 0, 0

    try:
        from .audio_utils import split_audio_by_silence
        duration = get_duration(wav_path)
        print(f"[Gemini STT] File {duration:.1f}s, lang={language}, speakers={num_speakers}")
        prompt = _build_prompt(num_speakers, language, custom_vocabulary)

        chunks = split_audio_by_silence(wav_path, chunk_length_sec=1200.0, max_chunk_sec=1500.0)
        if progress_callback:
            progress_callback(20, f"Đang gửi {len(chunks)} đoạn lên Google AI (xử lý song song)...")
        
        all_segments = []
        all_raw_words = []
        all_full_text = ""
        
        completed_chunks = set()
        if existing_segments:
            for s in existing_segments:
                if 'speaker_id' in s and s['speaker_id'].startswith('c') and '_' in s['speaker_id']:
                    try:
                        chunk_idx = int(s['speaker_id'].split('_')[0][1:])
                        completed_chunks.add(chunk_idx)
                    except: pass
        
        async def _process_single_chunk(session, idx, chunk_wav, offset, is_subchunk=False):
            try:
                if not is_subchunk and idx in completed_chunks:
                    print(f"[Gemini STT] Bỏ qua chunk {idx+1}/{len(chunks)} vì đã hoàn thành trước đó.")
                    return idx, None, None, None, None, None
                if is_subchunk:
                    print(f"[Gemini STT]   -> Sub-chunk {idx} - offset: {offset:.1f}s")
                else:
                    print(f"[Gemini STT] Bắt đầu chunk {idx+1}/{len(chunks)} - offset: {offset:.1f}s")
                
                chunk_duration = get_duration(chunk_wav)
                file_uri, file_name = await _upload_file(session, chunk_wav, api_key)
                chunk_error = None
                try:
                    gemini_segments, chunk_usage, chunk_error = await _call_gemini_stream(
                        session, file_uri, api_key, prompt, model_name,
                        max_tokens=65536
                    )

                    if chunk_error and chunk_error != "HALLUCINATION_DETECTED":
                        print(f"[Gemini STT] Error on chunk {idx+1}: {chunk_error}")
                        return idx, None, None, None, chunk_usage, chunk_error
                finally:
                    if not (chunk_error == "HALLUCINATION_DETECTED" and not is_subchunk):
                        await _delete_file(session, file_name, api_key)
                        if chunk_wav != wav_path:
                            try: os.remove(chunk_wav)
                            except: pass
                        
                if not gemini_segments:
                    return idx, None, None, None, chunk_usage, "Gemini trả về rỗng (có thể do safety filter hoặc file nhiễu)."

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
                    return idx, None, None, None, chunk_usage, "Sau khi lọc rác, chunk trống."

                raw_words = _segments_to_raw_words(clean_segments, file_duration=chunk_duration)
                segments = _words_to_segments(raw_words)
                
                for seg in segments:
                    seg["start"] = round(seg["start"] + offset, 2)
                    seg["end"] = round(seg["end"] + offset, 2)
                    seg["speaker_id"] = f"c{idx}_{seg['speaker_id']}"
                    seg["speaker"] = f"c{idx}_{seg.get('speaker', 'Speaker 1')}"
                    
                for w in raw_words:
                    w["start"] = round(w["start"] + offset, 2)
                    w["end"] = round(w["end"] + offset, 2)
                    w["speaker_id"] = f"c{idx}_{w['speaker_id']}"
                    
                chunk_text = " ".join(s.get("text", "") for s in clean_segments)
                
                if chunk_error == "HALLUCINATION_DETECTED" and not is_subchunk:
                    last_valid_timestamp = _parse_time(clean_segments[-1].get("end", 0))
                    if chunk_duration - last_valid_timestamp > 15:
                        print(f"[Gemini STT] ⚠️ Chunk {idx+1} ngáo ở giây {last_valid_timestamp:.1f}/{chunk_duration:.1f}s. Kích hoạt Smart Resume cắt nối tiếp...")
                        import pydub
                        audio = pydub.AudioSegment.from_wav(chunk_wav)
                        resume_audio = audio[int(last_valid_timestamp * 1000):]
                        resume_wav = chunk_wav.replace(".wav", f"_{idx}_resume.wav")
                        resume_audio.export(resume_wav, format="wav")
                        
                        _, r_segs, r_words, r_txt, r_use, r_err = await _process_single_chunk(
                            session, f"{idx}_resume", resume_wav, offset + last_valid_timestamp, is_subchunk=True
                        )
                        
                        try: os.remove(resume_wav)
                        except: pass
                            
                        if r_use:
                            for k in chunk_usage:
                                if k in r_use: chunk_usage[k] += r_use.get(k, 0)
                                
                        if r_segs: segments.extend(r_segs)
                        if r_words: raw_words.extend(r_words)
                        if r_txt: chunk_text += " " + r_txt

                return idx, segments, raw_words, chunk_text, chunk_usage, None
            except Exception as e:
                import traceback
                traceback.print_exc()
                return idx, None, None, None, None, str(e)

        completed_count = 0
        total_chunks = len(chunks)
        results = [None] * total_chunks

        total_in_all  = 0
        total_out_all = 0
        total_tok_all = 0
        chunk_errors = []

        # Hạn chế số kết nối đồng thời với connector (tăng luồng song song lên 15)
        connector = aiohttp.TCPConnector(limit=15)
        
        async with aiohttp.ClientSession(connector=connector, read_bufsize=20971520) as session:
            tasks = [
                _process_single_chunk(session, idx, chunk_wav, offset)
                for idx, (chunk_wav, offset) in enumerate(chunks)
            ]
            
            for future in asyncio.as_completed(tasks):
                try:
                    res_idx, segments, raw_words, chunk_text, chunk_usage, err_msg = await future
                    if err_msg:
                        chunk_errors.append(f"Chunk {res_idx+1}: {err_msg}")
                    results[res_idx] = (segments, raw_words, chunk_text)
                    if chunk_usage:
                        total_in_all  += chunk_usage.get("prompt_tokens", 0)
                        total_out_all += chunk_usage.get("completion_tokens", 0)
                        total_tok_all += chunk_usage.get("tokens_used", 0)
                except Exception as e:
                    chunk_errors.append(f"Lỗi không xác định: {str(e)}")
                    print(f"[Gemini STT] Exception in async processing: {e}")
                
                completed_count += 1
                if progress_callback:
                    progress_percent = int((completed_count / total_chunks) * 100)
                    progress_callback(progress_percent, f"Đang dịch (asyncio): xong {completed_count}/{total_chunks} phần...")

        for res in results:
            if not res: continue
            segments, raw_words, chunk_text = res
            if segments and raw_words:
                all_segments.extend(segments)
                all_raw_words.extend(raw_words)
                all_full_text += " " + chunk_text

        if existing_segments:
            # Lọc ra những segment thuộc các chunk đã hoàn thành
            for s in existing_segments:
                if 'speaker_id' in s and s['speaker_id'].startswith('c') and '_' in s['speaker_id']:
                    try:
                        chunk_idx = int(s['speaker_id'].split('_')[0][1:])
                        if chunk_idx in completed_chunks:
                            all_segments.append(s)
                            if 'text' in s:
                                all_full_text += " " + s['text']
                    except: pass
        
        # Sort all_segments by start time
        all_segments.sort(key=lambda x: x.get('start', 0))

        if chunk_errors:
            error_details = " | ".join(chunk_errors)
            return all_segments, all_raw_words, all_full_text.strip(), f"Lỗi xử lý file (Gemini): {error_details}", total_in_all, total_out_all

        if not all_segments:
            return [], [], "", "Gemini không nhận ra giọng nói trong file (file trống, nhiễu hoặc sai format).", 0, 0

        n_spk = len(set(s.get("speaker_id", "") for s in all_segments))
        PRICE_IN  = 1.50 / 1_000_000
        PRICE_OUT = 9.00 / 1_000_000
        total_cost = total_in_all * PRICE_IN + total_out_all * PRICE_OUT
        print(
            f"[Gemini STT] ✅ DONE: {len(all_segments)} segments, {n_spk} speakers, {len(chunks)} chunks\\n"
            f"💰 [Gemini STT] TỔNG CHI PHÍ FILE: "
            f"in={total_in_all:,} + out={total_out_all:,} = {total_tok_all:,} tokens | "
            f"cost=~${total_cost:.4f} USD ({len(chunks)} chunks)"
        )
        return all_segments, all_raw_words, all_full_text.strip(), None, 0, 0

    except Exception as e:
        import traceback
        traceback.print_exc()
        return [], [], "", f"Lỗi Gemini STT: {e}", 0, 0

