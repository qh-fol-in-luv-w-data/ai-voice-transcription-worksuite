import os
import frappe

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
            doc = frappe.get_doc("Agent", agent_name)
            val = doc.get_password("api_key")
            if val: return val
    except Exception: pass
    return os.getenv("OPENAI_API_KEY", "")

def get_elevenlabs_api_key():
    try:
        if frappe.db:
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("elevenlabs_api_key")
            if val: return val
    except Exception: pass
    return os.getenv("ELEVENLABS_API_KEY", "")

def get_worksuite_url():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.worksuite_url
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception: pass
    return os.getenv("WORKSUITE_URL", "https://deverp.ctgroupvietnam.com")

def get_worksuite_email():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.worksuite_email
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception: pass
    return os.getenv("WORKSUITE_EMAIL", "ai.worksuit.dev@ctmcorp.com.vn")

def get_worksuite_password():
    try:
        if frappe.db:
            frappe.flags.ignore_permissions = True
            doc = frappe.get_doc("Voice App Settings")
            val = doc.get_password("worksuite_password")
            frappe.flags.ignore_permissions = False
            if val: return val
    except Exception: pass
    return os.getenv("WORKSUITE_PASSWORD", "")

MIN_SPEAKERS = None
MAX_SPEAKERS = 8
DEFAULT_LANG = "vi"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEAKER_DB_PATH = os.path.join(BASE_DIR, "speaker_db.json")
SIMILARITY_THRESHOLD = 0.5   # Nhận diện speaker từ DB khi similarity >= 0.5
LANGUAGES = [
    ("Tiếng Việt", "vi"), ("English", "en"), ("日本語", "ja"),
    ("中文", "zh"), ("한국어", "ko"), ("Français", "fr"),
    ("Deutsch", "de"), ("Español", "es"), ("Auto detect", "auto"),
]
ENROLL_SAMPLE_TEXT = """
Hệ thống nhận diện giọng nói AI đang ngày càng trở nên phổ biến...
"""