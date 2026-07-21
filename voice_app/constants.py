import os
import frappe
from dotenv import load_dotenv

# Try to load .env from bench directory
try:
    load_dotenv(os.path.join(frappe.utils.get_bench_path(), ".env"))
except Exception:
    pass

# ── CONFIG ────────────────────────────────────────────────────────────────────
def get_whisper_url():
    try:
        if frappe.db:
            val = frappe.db.get_single_value("Voice App Settings", "whisper_url")
            if val: return val
    except Exception: pass
    return os.getenv("WHISPER_URL", "http://localhost:8080/inference")

def get_hf_token():
    try:
        if frappe.db:
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("hf_token")
            if val: return val
    except Exception: pass
    return os.getenv("HF_TOKEN", "")

AGENT_NAME = "2AS-WORKSUITE"

def get_openai_api_key(agent_name=AGENT_NAME):
    try:
        if frappe.db:
            doc = frappe.get_single("Voice App Settings")
            try:
                val = doc.get_password("openai_api_key")
                if val: return val
            except Exception:
                pass
        
        # Fallback to site_config.json
        if frappe.conf.get("openai_api_key"):
            return frappe.conf.get("openai_api_key")
    except Exception: pass
    return os.getenv("OPENAI_API_KEY", "")


def get_gemini_api_key():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("gemini_api_key")
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception: pass
    return os.getenv("GEMINI_API_KEY", "")


def get_gemini_model():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.gemini_model
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception: pass
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


def get_elevenlabs_api_key():
    try:
        if frappe.db:
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("elevenlabs_api_key")
            if val: return val
    except Exception: pass
    return os.getenv("ELEVENLABS_API_KEY", "")

def get_gemini_api_key():
    """Gemini API key from the Voice App Settings singleton."""
    try:
        if frappe.db:
            doc = frappe.get_single("Voice App Settings")
            val = doc.get_password("gemini_api_key")
            if val:
                return val
    except Exception:
        pass
    return ""

def get_gemini_model():
    """Gemini model from the Voice App Settings singleton."""
    try:
        if frappe.db:
            val = frappe.db.get_single_value("Voice App Settings", "gemini_model")
            if val:
                return str(val).strip()
    except Exception:
        pass
    return ""

def get_worksuite_url():
    val = None
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.sync_api_url or doc.worksuite_url
            frappe.flags.ignore_permissions = False
    except Exception: pass
    if not val:
        val = os.getenv("WORKSUITE_URL", "https://cterp.ctgroupvietnam.com")
    val = val.strip()
    if not val.startswith("http://") and not val.startswith("https://"):
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
    except Exception: pass
    return os.getenv("WORKSUITE_TOKEN", "b88248d0241d472:94a1889151c0543")

def get_google_service_account_path():
    """Đường dẫn file JSON service account Google."""
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.google_sa_path
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception: pass
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
    except Exception: pass
    return os.getenv("GOOGLE_GCS_BUCKET", "pai-stt")

MIN_SPEAKERS = None
MAX_SPEAKERS = 8
DEFAULT_LANG = "vi"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEAKER_DB_PATH = os.path.join(BASE_DIR, "speaker_db.json")
SIMILARITY_THRESHOLD = 0.65  # Nhận diện speaker từ DB khi similarity >= 0.5
MERGE_THRESHOLD = 0.5      # Gộp các speaker giống nhau khi similarity >= 0.45
LANGUAGES = [
    ("Tiếng Việt", "vi"), ("English", "en"), ("日本語", "ja"),
    ("中文", "zh"), ("한국어", "ko"), ("Français", "fr"),
    ("Deutsch", "de"), ("Español", "es"), ("Auto detect", "auto"),
]
ENROLL_SAMPLE_TEXT = """
Hệ thống nhận diện giọng nói AI đang ngày càng trở nên phổ biến...
"""
