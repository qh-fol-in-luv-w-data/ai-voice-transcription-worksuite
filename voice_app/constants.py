import os
from dotenv import load_dotenv
import frappe

# Load .env file
load_dotenv()

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

AGENT_NAME = "2AS-WORKSUITE"  # Đổi thành ID/Tên Agent thực tế của app này trong bảng Agent

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

MIN_SPEAKERS = None
MAX_SPEAKERS = 8
DEFAULT_LANG = "vi"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEAKER_DB_PATH = os.path.join(BASE_DIR, "speaker_db.json")
SIMILARITY_THRESHOLD = 0.3
LANGUAGES = [
    ("Tiếng Việt", "vi"), ("English", "en"), ("日本語", "ja"),
    ("中文", "zh"), ("한국어", "ko"), ("Français", "fr"),
    ("Deutsch", "de"), ("Español", "es"), ("Auto detect", "auto"),
]
ENROLL_SAMPLE_TEXT = """
Hệ thống nhận diện giọng nói AI đang ngày càng trở nên phổ biến...
"""