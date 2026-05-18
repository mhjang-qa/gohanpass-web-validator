import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, RUNS_DIR


SCHEDULE_FILE = DATA_DIR / "schedule.json"


def read_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_schedule() -> dict:
    return read_json(
        SCHEDULE_FILE,
        {
            "enabled": False,
            "time": "09:00",
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "scenarios": [],
            "notion_upload": True,
        },
    )


def save_schedule(schedule: dict):
    write_json(SCHEDULE_FILE, schedule)


def save_run(run: dict):
    write_json(RUNS_DIR / f"{run['id']}.json", run)


def load_run(run_id: str) -> dict | None:
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    return read_json(path, None)


def list_runs(limit: int = 30) -> list[dict]:
    runs = []
    for path in sorted(RUNS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        run = read_json(path, None)
        if run:
            runs.append(run)
        if len(runs) >= limit:
            break
    return runs
