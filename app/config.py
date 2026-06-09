import os
import secrets
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BASE_DIR / ".env")


def resolve_path(value: str, default: Path) -> Path:
    raw = os.getenv(value)
    if not raw:
        return default.resolve()

    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


SCENARIO_DIR = resolve_path("SCENARIO_DIR", BASE_DIR / "scenarios")
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
OUTPUT_DIR = BASE_DIR / "output"
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
NOTION_UPLOAD = os.getenv("NOTION_UPLOAD", "true").lower() != "false"
TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
API_BASE_URL = os.getenv("API_BASE_URL", "https://go.hanpass.com").rstrip("/")
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "15"))
API_TOKEN = os.getenv("API_TOKEN", "")
API_HEADERS = os.getenv("API_HEADERS", "")
VALIDATOR_USER = os.getenv("VALIDATOR_USER", "qa").strip()
VALIDATOR_PASSWORD = os.getenv("VALIDATOR_PASSWORD", "qa")
VALIDATOR_SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip() or secrets.token_urlsafe(48)
VALIDATOR_SESSION_MINUTES = max(1, int(os.getenv("VALIDATOR_SESSION_MINUTES", "720")))
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"}
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "none").lower()
QA_CONSOLE_SHARED_SECRET = os.getenv("QA_CONSOLE_SHARED_SECRET", "").strip()
QA_CONSOLE_ALLOWED_ORIGIN = os.getenv(
    "QA_CONSOLE_ALLOWED_ORIGIN",
    "https://gohanpass-qa-console.onrender.com",
).rstrip("/")

DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
