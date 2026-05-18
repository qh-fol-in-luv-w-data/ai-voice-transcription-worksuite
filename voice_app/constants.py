import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────────────────────
WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:8080/inference")
HF_TOKEN = os.getenv("HF_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
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