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
            "snapshot_interval_seconds": 30,
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


def mark_running_runs_interrupted():
    for path in RUNS_DIR.glob("*.json"):
        run = read_json(path, None)
        if not run or run.get("status") != "running":
            continue

        summary = run.setdefault("summary", {})
        summary["total"] = int(summary.get("total") or 0)
        summary["pass"] = int(summary.get("pass") or 0)
        summary["fail"] = int(summary.get("fail") or 0)
        summary["na"] = int(summary.get("na") or 0)
        summary["error"] = max(1, int(summary.get("error") or 0))
        run["status"] = "failed"
        run.setdefault("logs", []).append(
            "⚠️ 서버 재시작으로 실행이 중단되어 실패 처리되었습니다."
        )
        run["progress"] = {
            **run.get("progress", {}),
            "percent": 100,
            "label": "서버 재시작으로 실행 중단",
        }
        write_json(path, run)
