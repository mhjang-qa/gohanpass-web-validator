import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.auth import (
    AUTH_COOKIE,
    clear_auth_cookie,
    create_manual_session,
    issue_auth_cookie,
    read_auth_session,
    verify_manual_credentials,
)
from app.config import BASE_DIR, OUTPUT_DIR
import app.runner as runner
from app.scenarios import list_scenarios
from app.scheduler import apply_schedule, start_scheduler, stop_scheduler
from app.sso import (
    QA_CONSOLE_ALLOWED_ORIGIN,
    build_console_session,
    is_allowed_console_referer,
    launch_failure_html,
    launch_success_html,
    logout_cleanup_html,
    validate_sso_token,
)
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


class LoginRequest(BaseModel):
    username: str
    password: str


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


@app.get("/api/auth/bootstrap")
async def api_auth_bootstrap(request: Request):
    session, reason = read_auth_session(request.cookies.get(AUTH_COOKIE))
    payload = {
        "allowedOrigin": QA_CONSOLE_ALLOWED_ORIGIN,
        "authenticated": bool(session),
        "session": session,
        "reason": reason,
    }
    if not reason:
        return payload

    response = JSONResponse(payload)
    clear_auth_cookie(response)
    return response


@app.post("/api/auth/login")
async def api_auth_login(request: LoginRequest):
    if not verify_manual_credentials(request.username, request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    session = create_manual_session(request.username)
    response = JSONResponse({"authenticated": True, "session": session})
    issue_auth_cookie(response, session)
    return response


@app.post("/api/auth/logout")
async def api_auth_logout():
    response = JSONResponse({"ok": True})
    clear_auth_cookie(response)
    return response


@app.get("/sso/launch", response_class=HTMLResponse)
async def sso_launch(request: Request, qa_console_token: str = ""):
    payload, reason = validate_sso_token(qa_console_token)
    if not payload or not is_allowed_console_referer(request.headers.get("referer")):
        failure = launch_failure_html(reason or "forbidden")
        response = HTMLResponse(failure, status_code=status.HTTP_401_UNAUTHORIZED)
        clear_auth_cookie(response)
        return response

    session = build_console_session(payload)
    response = HTMLResponse(launch_success_html(session))
    issue_auth_cookie(response, session)
    return response


@app.get("/sso/logout", response_class=HTMLResponse)
async def sso_logout():
    response = HTMLResponse(logout_cleanup_html())
    clear_auth_cookie(response)
    return response


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
