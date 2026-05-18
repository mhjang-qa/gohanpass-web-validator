import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import BASE_DIR
from app.runner import run_scenarios
from app.scenarios import list_scenarios
from app.scheduler import apply_schedule, start_scheduler, stop_scheduler
from app.storage import list_runs, load_run, load_schedule


app = FastAPI(title="GO Hanpass Web Auto Validator")
STATIC_DIR = BASE_DIR / "app" / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RunRequest(BaseModel):
    scenarios: list[str]
    notion_upload: bool = True


class ScheduleRequest(BaseModel):
    enabled: bool
    time: str
    days: list[str]
    scenarios: list[str]
    notion_upload: bool = True


@app.on_event("startup")
async def on_startup():
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/scenarios")
async def api_scenarios():
    return {"scenarios": list_scenarios()}


@app.get("/api/runs")
async def api_runs():
    return {"runs": list_runs()}


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
        run = await run_scenarios(request.scenarios, notion_upload=request.notion_upload, source="manual")
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
