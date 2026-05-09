"""Application configuration loaded from .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    SECRET_KEY = _get("SECRET_KEY", "dev-secret-change-me")
    ADMIN_PASSWORD = _get("ADMIN_PASSWORD", "admin123")
    FACE_TOLERANCE = float(_get("FACE_TOLERANCE", "0.5"))
    SERIAL_PORT = _get("SERIAL_PORT", "")
    SERIAL_BAUD = int(_get("SERIAL_BAUD", "115200"))
    ELECTION_TITLE = _get("ELECTION_TITLE", "Smart Digital Voting Machine")

    DATA_DIR = BASE_DIR / "data"
    FACES_DIR = DATA_DIR / "faces"
    CANDIDATES_DIR = DATA_DIR / "candidates"
    DB_PATH = DATA_DIR / "voting.db"

    MAX_UPLOAD_MB = 4
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024


def ensure_dirs() -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.FACES_DIR.mkdir(parents=True, exist_ok=True)
    Config.CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
