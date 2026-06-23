import os
from typing import List, Dict, Any, Tuple
from elevenlabs.client import ElevenLabs
from .constants import get_elevenlabs_api_key

def call_elevenlabs_stt(wav_path: str, language: str = "vi", num_speakers: int = None) -> tuple:
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
        # Keyterms: gợi ý từ khoá nghiệp vụ để tăng độ chính xác nhận dạng
        KEYTERMS = [
            # --- Tiếng Việt nghiệp vụ ---
            "tờ trình", "kế hoạch", "doanh thu", "báo cáo", "hợp đồng",
            "dự án", "ngân sách", "phòng ban", "công ty", "quản lý",
            "nghiệm thu", "thanh lý", "đề xuất", "phê duyệt", "triển khai",
            "tiến độ", "rủi ro", "chi phí", "lợi nhuận", "quyết toán",

            # --- CT Group: tập đoàn & công ty thành viên ---
            "CT Group", "CT Corp", "CTM", "CTEC", "DAIT",
            "CT UAV", "CT Semiconductor", "CT Modulex", "Modulex",
            "CT Verse", "CT Solar Homes", "CT Innovation Hub",
            "CTrans Auto", "CTOptimal", "GASCO", "VGCT", "Diginal",
            "Carbondo", "CCTPA", "Airbility", "SkyDrive",

            # --- CT Group: hệ thống & nền tảng ---
            "Worksuite", "2AS", "iMaster", "ERP", "CRM", "HRM",
            "NDT 15", "CarbonFly", "Catalyst", "Sustain.Life",
            "LAE", "OSAT", "ATP", "CTDA200M", "eVTOL", "UAV", "UAM",
            "LiDAR", "SoC", "MCU", "NPU", "ADC", "DAC", "NDT",

            # --- Quản lý dự án (Project Management) ---
            "deadline", "milestone", "sprint", "backlog", "roadmap",
            "kickoff", "handover", "deliverable", "stakeholder", "scope",
            "timeline", "escalation", "sign-off", "go-live", "rollout",
            "Agile", "Scrum", "Kanban", "Waterfall",

            # --- Tài chính / Kế toán (Finance) ---
            "KPI", "OKR", "ROI", "P&L", "EBITDA", "revenue", "budget",
            "invoice", "purchase order", "PO", "capex", "opex",
            "cash flow", "cost center", "profit margin", "breakeven",

            # --- IT / Công nghệ (Technology) ---
            "API", "backend", "frontend", "database", "server", "cloud",
            "deployment", "Docker", "Kubernetes", "CI/CD", "DevOps",
            "microservice", "pipeline", "repository", "Git", "branch",
            "Python", "JavaScript", "Vue", "React", "Node.js", "Frappe",

            # --- Nhân sự / HR ---
            "onboarding", "offboarding", "headcount", "recruitment",
            "performance review", "probation", "payroll", "offer letter",
            "job description", "KPIs", "OKRs",

            # --- Từ viết tắt phổ biến trong họp ---
            "ASAP", "FYI", "TBD", "TBC", "EOD", "EOM", "ETA",
            "Q1", "Q2", "Q3", "Q4", "YTD", "MoM", "YoY",
        ]

        with open(wav_path, "rb") as f:
            result = client.speech_to_text.convert(
                file=f,
                model_id="scribe_v2",
                diarize=True,
                tag_audio_events=False,
                language_code=language if language != "auto" else None,
                num_speakers=num_speakers if num_speakers else None,
                # diarization_threshold chỉ dùng được khi num_speakers=None
                diarization_threshold=0.12 if not num_speakers else None,
                keyterms=KEYTERMS,
                temperature=0,  # deterministic output, tốt nhất cho transcription
            )
        print(f"[ElevenLabs] num_speakers={num_speakers}, diarization_threshold={'0.12' if not num_speakers else 'N/A'}, temperature=0")
        
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
        
        # Gộp words thành segments theo speaker, đồng thời giữ lại raw_words để re-diarize
        segments = []
        raw_words = []
        current_segment = None

        if hasattr(result, 'words') and result.words:
            for word in result.words:
                if word.start is None or word.end is None:
                    continue
                # Thu thập raw words (chỉ lấy word type, bỏ space/punct)
                if word.text and word.text.strip():
                    raw_words.append({
                        "start":      word.start,
                        "end":        word.end,
                        "text":       word.text,
                        "speaker_id": word.speaker_id,
                    })
                # Gộp segment theo ElevenLabs speaker_id (dùng làm fallback)
                if current_segment is None or current_segment["speaker_id"] != word.speaker_id:
                    if current_segment is not None:
                        segments.append(current_segment)
                    current_segment = {
                        "start":      word.start,
                        "end":        word.end,
                        "speaker_id": word.speaker_id,
                        "text":       word.text,
                    }
                else:
                    current_segment["end"]   = word.end
                    current_segment["text"] += " " + word.text

            if current_segment is not None:
                segments.append(current_segment)

        full_text = result.text if hasattr(result, 'text') else " ".join([s["text"] for s in segments])

        if chars_used <= 0 and full_text:
            chars_used = len(full_text)

        return segments, raw_words, full_text, None, chars_used, chars_remaining

    except Exception as e:
        return [], [], "", f"Lỗi ElevenLabs: {str(e)}", 0, 0

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
