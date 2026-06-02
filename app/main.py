import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import BASE_DIR, OUTPUT_DIR
import app.runner as runner
from app.scenarios import list_scenarios
from app.scheduler import apply_schedule, start_scheduler, stop_scheduler
from app.storage import list_runs, load_run, load_schedule, mark_running_runs_interrupted


app = FastAPI(title="GO Hanpass Web Auto Validator")
STATIC_DIR = BASE_DIR / "app" / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")


class RunRequest(BaseModel):
    scenarios: list[str]
    notion_upload: bool = True
    snapshot_interval_seconds: int = 30
    target_environment: str = "prod"


class ScheduleRequest(BaseModel):
    enabled: bool
    time: str
    days: list[str]
    scenarios: list[str]
    notion_upload: bool = True
    snapshot_interval_seconds: int = 30
    target_environment: str = "prod"


@app.get("/api/current-run")
async def api_current_run():
    if not runner.CURRENT_RUN_ID:
        return {"run": None}
    run = runner.get_current_run() or load_run(runner.CURRENT_RUN_ID)
    return {"run": run}


@app.on_event("startup")
async def on_startup():
    mark_running_runs_interrupted()
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()


@app.get("/")
async def index():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/scenarios")
async def api_scenarios():
    return {"scenarios": list_scenarios()}


@app.get("/api/runs")
async def api_runs():
    runs = list_runs()
    current_run = runner.get_current_run()
    if current_run and not any(run.get("id") == current_run.get("id") for run in runs):
        runs.insert(0, current_run)
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
async def api_run(run_id: str):
    run = load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/runs")
async def api_start_run(request: RunRequest):
    if not request.scenarios:
        raise HTTPException(status_code=400, detail="scenarios required")
    try:
        run = runner.start_run_scenarios(
            request.scenarios,
            notion_upload=request.notion_upload,
            source="manual",
            snapshot_interval_seconds=request.snapshot_interval_seconds,
            target_environment=request.target_environment,
        )
        return run
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/schedule")
async def api_get_schedule():
    return load_schedule()


@app.post("/api/schedule")
async def api_save_schedule(request: ScheduleRequest):
    schedule = request.dict()
    apply_schedule(schedule)
    return schedule
