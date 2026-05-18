import os
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

DATA_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
