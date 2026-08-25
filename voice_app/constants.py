import os
import frappe
from dotenv import load_dotenv

def _log_config_error(title, exc):
    try:
        frappe.log_error(str(exc), title)
    except Exception:
        return

# Try to load .env from bench directory
try:
    load_dotenv(os.path.join(frappe.utils.get_bench_path(), ".env"))
except Exception as exc:
    _log_config_error("Voice App dotenv load failed", exc)

# ── CONFIG ────────────────────────────────────────────────────────────────────
def get_whisper_url():
    try:
        if frappe.db:
            val = frappe.db.get_single_value("Voice App Settings", "whisper_url")
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App whisper URL lookup failed", exc)
    return os.getenv("WHISPER_URL", "http://localhost:8080/inference")

def get_hf_token():
    try:
        if frappe.db:
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("hf_token")
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App HF token lookup failed", exc)
    return os.getenv("HF_TOKEN", "")

AGENT_NAME = "2AS-WORKSUITE"

def get_openai_api_key(agent_name=AGENT_NAME):
    try:
        if frappe.db:
            doc = frappe.get_single("Voice App Settings")
            try:
                val = doc.get_password("openai_api_key")
                if val: return val
            except Exception as exc:
                _log_config_error("Voice App OpenAI password lookup failed", exc)
        
        # Fallback to site_config.json
        if frappe.conf.get("openai_api_key"):
            return frappe.conf.get("openai_api_key")
    except Exception as exc:
        _log_config_error("Voice App OpenAI key lookup failed", exc)
    return os.getenv("OPENAI_API_KEY", "")


def get_gemini_api_key():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("gemini_api_key")
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App Gemini key lookup failed", exc)
    return os.getenv("GEMINI_API_KEY", "")


def get_gemini_model():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.gemini_model
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App Gemini model lookup failed", exc)
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


def get_elevenlabs_api_key():
    try:
        if frappe.db:
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("elevenlabs_api_key")
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App ElevenLabs key lookup failed", exc)
    return os.getenv("ELEVENLABS_API_KEY", "")

def get_gemini_api_key():
    """Gemini API key from the Voice App Settings singleton."""
    try:
        if frappe.db:
            doc = frappe.get_single("Voice App Settings")
            val = doc.get_password("gemini_api_key")
            if val:
                return val
    except Exception as exc:
        _log_config_error("Voice App Gemini singleton key lookup failed", exc)
    return ""

def get_gemini_model():
    """Gemini model from the Voice App Settings singleton."""
    try:
        if frappe.db:
            val = frappe.db.get_single_value("Voice App Settings", "gemini_model")
            if val:
                return str(val).strip()
    except Exception as exc:
        _log_config_error("Voice App Gemini singleton model lookup failed", exc)
    return ""

def get_gemini_stt_max_output_tokens():
    """Maximum Gemini output tokens per STT chunk."""
    default = 64000
    try:
        if hasattr(frappe, "db") and frappe.db:
            val = frappe.db.get_single_value("Voice App Settings", "gemini_stt_max_output_tokens")
            if val:
                return max(4000, int(val))
    except Exception:
        pass
    try:
        return max(4000, int(os.getenv("GEMINI_STT_MAX_OUTPUT_TOKENS", default)))
    except (TypeError, ValueError):
        return default

def get_worksuite_url():
    val = None
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.sync_api_url or doc.worksuite_url
            frappe.flags.ignore_permissions = False
    except Exception as exc:
        _log_config_error("Voice App Worksuite URL lookup failed", exc)
    if not val:
        val = os.getenv("WORKSUITE_URL", "https://cterp.ctgroupvietnam.com")
    val = val.strip()
    if val.startswith("http://"):
        val = "https://" + val[len("http://"):]
    elif not val.startswith("https://"):
        val = "https://" + val
    return val.rstrip("/")

def get_worksuite_token():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("sync_api_token") or doc.get_password("worksuite_token")
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App Worksuite token lookup failed", exc)
    return os.getenv("WORKSUITE_TOKEN", "")

def get_google_service_account_path():
    """Đường dẫn file JSON service account Google."""
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.google_sa_path
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App Google service account lookup failed", exc)
    return os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

def get_google_gcs_bucket():
    """GCS bucket để upload file dài."""
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.google_gcs_bucket
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception as exc:
        _log_config_error("Voice App Google GCS bucket lookup failed", exc)
    return os.getenv("GOOGLE_GCS_BUCKET", "pai-stt")

MIN_SPEAKERS = None
MAX_SPEAKERS = 8
DEFAULT_LANG = "vi"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEAKER_DB_PATH = os.path.join(BASE_DIR, "speaker_db.json")
# Ngưỡng chấp nhận người có cosine similarity cao nhất trong Voice DB.
# Dưới 0.50 giữ là Speaker/Người lạ, không đoán tên.
SIMILARITY_THRESHOLD = 0.50
# ==============================================================================
# NGƯỠNG GỘP NHÓM (CLUSTERING THRESHOLD)
# - Dùng khi gộp các Speaker không có trong DB (Speaker) thành các cụm.
# - Nếu độ tương đồng cosine >= MERGE_THRESHOLD, gộp chung nhóm.
MERGE_THRESHOLD = 0.45
# ==============================================================================
LANGUAGES = [
    ("Tiếng Việt", "vi"), ("English", "en"), ("日本語", "ja"),
    ("中文", "zh"), ("한국어", "ko"), ("Français", "fr"),
    ("Deutsch", "de"), ("Español", "es"), ("Auto detect", "auto"),
]
ENROLL_SAMPLE_TEXT = """
Hệ thống nhận diện giọng nói AI đang ngày càng trở nên phổ biến...
"""
