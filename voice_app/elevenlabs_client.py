import os
from typing import List, Dict, Any, Tuple
from elevenlabs.client import ElevenLabs
from .constants import get_elevenlabs_api_key

def call_elevenlabs_stt(wav_path: str, language: str = "vi") -> tuple:
    """
    Gọi ElevenLabs Speech-to-Text API với diarization.
    Trả về: (segments, full_text, error, chars_used, chars_remaining)
    """
    api_key = get_elevenlabs_api_key()
    if not api_key:
        return [], "", "Thiếu ELEVENLABS_API_KEY trong cấu hình", 0, 0

    client = ElevenLabs(api_key=api_key)
    
    # Lấy số dư trước
    chars_before = 0
    chars_limit = 0
    try:
        sub_before = client.user.subscription.get()
        chars_before = sub_before.character_count or 0
        chars_limit = sub_before.character_limit or 0
    except Exception:
        pass
    
    try:
        with open(wav_path, "rb") as f:
            # Gọi API
            result = client.speech_to_text.convert(
                file=f,
                model_id="scribe_v2",
                diarize=True,
                language_code=language if language != "auto" else "vi"
            )
        
        # Lấy số dư sau
        chars_after = chars_before
        try:
            sub_after = client.user.subscription.get()
            chars_after = sub_after.character_count or 0
            chars_limit = sub_after.character_limit or 0
        except Exception:
            pass
        
        chars_used = max(0, chars_after - chars_before)
        chars_remaining = max(0, chars_limit - chars_after)
        
        # Kết quả trả về chứa .words hoặc .text. Ta cần gộp words thành các đoạn theo speaker
        segments = []
        current_segment = None
        
        if hasattr(result, 'words') and result.words:
            for word in result.words:
                if current_segment is None or current_segment["speaker_id"] != word.speaker_id:
                    if current_segment is not None:
                        segments.append(current_segment)
                    
                    current_segment = {
                        "start": word.start,
                        "end": word.end,
                        "speaker_id": word.speaker_id,
                        "text": word.text
                    }
                else:
                    current_segment["end"] = word.end
                    current_segment["text"] += " " + word.text
            
            if current_segment is not None:
                segments.append(current_segment)
        
        full_text = result.text if hasattr(result, 'text') else " ".join([s["text"] for s in segments])
        
        if chars_used <= 0 and full_text:
            chars_used = len(full_text)
            
        return segments, full_text, None, chars_used, chars_remaining

    except Exception as e:
        return [], "", f"Lỗi ElevenLabs: {str(e)}", 0, 0

def check_elevenlabs_balance() -> str:
    api_key = get_elevenlabs_api_key()
    if not api_key:
        return "Thiếu ELEVENLABS_API_KEY"
    try:
        client = ElevenLabs(api_key=api_key)
        sub = client.user.subscription.get()
        used = sub.character_count
        total = sub.character_limit
        return f"Số dư ElevenLabs: Đã dùng {used:,} / {total:,} tokens ({(used/total)*100 if total else 0:.1f}%)"
    except Exception as e:
        if "missing_permissions" in str(e).lower() or "user_read" in str(e).lower():
            return "❌ API Key của bạn không có quyền 'Read User'. Vui lòng cấp quyền này trên trang ElevenLabs để xem số dư!"
        return f"❌ Lỗi check số dư: {str(e)}"
