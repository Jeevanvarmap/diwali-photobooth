import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PHOTO_COUNT = 3
COUNTDOWN_SECONDS = 10
HOLD_STILL_SECONDS = 2
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1350

OUTPUT_DIR = ROOT / "output"
BACKGROUNDS_DIR = ROOT / "assets" / "backgrounds"
STATIC_DIR = ROOT / "static"
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.json"
DRIVE_FOLDER_NAME = "Diwali Photobooth"

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip()
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image").strip()


def ai_available() -> bool:
    if AI_PROVIDER == "gemini":
        return bool(GEMINI_API_KEY)
    if AI_PROVIDER == "openai":
        return bool(OPENAI_API_KEY)
    return False
