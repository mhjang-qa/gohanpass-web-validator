import asyncio
import importlib.util
import subprocess
import sys
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

from app.config import HEADLESS, OUTPUT_DIR, SCENARIO_DIR, TIMEZONE
from app.notion import upload_to_notion
from app.scenarios import resolve_scenario_paths
from app.storage import save_run


RUN_LOCK = asyncio.Lock()
CURRENT_RUN_ID: str | None = None
RUN_TASKS: dict[str, asyncio.Task] = {}


def now_iso() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")


def classify_status(status: str) -> str:
    upper = str(status).upper()
    if upper.startswith("PASS"):
        return "pass"
    if upper.startswith(("NA", "N/A")):
        return "na"
    return "fail"


def create_run_record(scenario_names: list[str], source: str, run_id: str | None = None) -> tuple[dict, list[Path]]:
    run_id = run_id or datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y%m%d_%H%M%S")
    scenario_paths = resolve_scenario_paths(scenario_names)
    run = {
        "id": run_id,
        "source": source,
        "status": "running",
        "started_at": now_iso(),
        "finished_at": None,
        "scenarios": [],
        "summary": {"total": 0, "pass": 0, "fail": 0, "na": 0},
        "logs": [],
        "snapshots": [],
        "attachments": [],
        "notion": None,
    }
    save_run(run)
    return run, scenario_paths


def append_run_log(run: dict, message: str):
    run["logs"].append(message)
    save_run(run)


async def capture_snapshot(run: dict, page, label: str = "live") -> None:
    snapshot_dir = OUTPUT_DIR / run["id"] / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H%M%S")
    filename = f"{label}_{len(run['snapshots']) + 1:03d}_{timestamp}.png"
    file_path = snapshot_dir / filename
    try:
        await page.screenshot(path=str(file_path), full_page=False)
        run["snapshots"].append(f"/output/{run['id']}/snapshots/{filename}")
        save_run(run)
        append_run_log(run, f"📸 스냅샷 저장: {filename}")
    except Exception as exc:
        append_run_log(run, f"📸 스냅샷 실패: {exc}")


async def snapshot_loop(run: dict, page, stop_event: asyncio.Event) -> None:
    await capture_snapshot(run, page, label="start")
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10)
        except asyncio.TimeoutError:
            if stop_event.is_set():
                break
            await capture_snapshot(run, page)


async def execute_run(run: dict, scenario_paths: list[Path], notion_upload: bool = True) -> dict:
    global CURRENT_RUN_ID

    CURRENT_RUN_ID = run["id"]
    playwright = browser = context = page = None
    snapshot_stop = asyncio.Event()
    snapshot_task: asyncio.Task | None = None
    try:
        playwright, browser, context, page = await create_page()
        snapshot_task = asyncio.create_task(snapshot_loop(run, page, snapshot_stop))
        for idx, path in enumerate(scenario_paths, 1):
            append_run_log(run, f"[{idx}/{len(scenario_paths)}] {path.name} 시작")
            scenario_result = {"name": path.name, "results": []}
            try:
                module = import_scenario(path)
                if hasattr(module, "log"):
                    module.log.logger = lambda message: append_run_log(run, message)
                auth_module = sys.modules.get("scenarios._auth")
                if auth_module and hasattr(auth_module, "log"):
                    auth_module.log.logger = lambda message: append_run_log(run, message)

                raw_results = await module.run(page)
            except Exception as exc:
                raw_results = [("scenario_execution", f"FAIL ({exc})")]
                append_run_log(run, f"{path.name} 실패: {exc}")

            for name, status in raw_results:
                kind = classify_status(status)
                run["summary"]["total"] += 1
                run["summary"][kind] += 1
                scenario_result["results"].append({"name": str(name), "status": str(status)})

            run["scenarios"].append(scenario_result)
            save_run(run)

        screenshot_path = OUTPUT_DIR / f"{run['id']}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        run["attachments"].append(str(screenshot_path))

        log_path = OUTPUT_DIR / f"{run['id']}.log"
        log_path.write_text("\n".join(run["logs"]), encoding="utf-8")
        run["attachments"].append(str(log_path))

        if notion_upload:
            notion_result = upload_to_notion(run)
            run["notion"] = {"uploaded": True, "page_id": notion_result.get("id") if notion_result else None}

        run["status"] = "completed" if run["summary"]["fail"] == 0 else "failed"
        return run
    except Exception as exc:
        run["status"] = "failed"
        append_run_log(run, f"실행 오류: {exc}")
        return run
    finally:
        run["finished_at"] = now_iso()
        save_run(run)
        CURRENT_RUN_ID = None
        snapshot_stop.set()
        if snapshot_task:
            snapshot_task.cancel()
            with suppress(asyncio.CancelledError):
                await snapshot_task
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def run_scenarios(scenario_names: list[str], notion_upload: bool = True, source: str = "manual", run_id: str | None = None) -> dict:
    if RUN_LOCK.locked() or any(not task.done() for task in RUN_TASKS.values()):
        raise RuntimeError("이미 실행 중인 작업이 있습니다.")

    async with RUN_LOCK:
        run, scenario_paths = create_run_record(scenario_names, source, run_id=run_id)
        return await execute_run(run, scenario_paths, notion_upload=notion_upload)


def start_run_scenarios(scenario_names: list[str], notion_upload: bool = True, source: str = "manual", run_id: str | None = None) -> dict:
    if RUN_LOCK.locked() or any(not task.done() for task in RUN_TASKS.values()):
        raise RuntimeError("이미 실행 중인 작업이 있습니다.")

    run, scenario_paths = create_run_record(scenario_names, source, run_id=run_id)
    task = asyncio.create_task(run_scenarios_background(run, scenario_paths, notion_upload=notion_upload))
    RUN_TASKS[run["id"]] = task
    task.add_done_callback(lambda _: RUN_TASKS.pop(run["id"], None))
    return run


async def run_scenarios_background(run: dict, scenario_paths: list[Path], notion_upload: bool = True) -> dict:
    async with RUN_LOCK:
        return await execute_run(run, scenario_paths, notion_upload=notion_upload)


async def create_page():
    playwright = await async_playwright().start()
    launch_options = {
        "headless": HEADLESS,
        "args": [
            "--window-size=500,920",
            "--force-device-scale-factor=1",
            "--disable-features=TranslateUI",
            "--lang=ko-KR",
            "--disable-translate",
            "--no-first-run",
        ],
    }

    async def launch_browser():
        return await playwright.chromium.launch(**launch_options)

    async def install_browsers():
        command = [
            sys.executable,
            "-m",
            "playwright",
            "install",
            "chromium",
            "chromium-headless-shell",
        ]
        await asyncio.to_thread(
            subprocess.run,
            command,
            check=True,
            capture_output=True,
            text=True,
        )

    def should_recover(error: Exception) -> bool:
        message = str(error)
        return "Executable doesn't exist" in message or "Looks like Playwright was just installed" in message

    try:
        browser = await launch_browser()
    except Exception as exc:
        if not should_recover(exc):
            await playwright.stop()
            raise
        try:
            await install_browsers()
            browser = await launch_browser()
        except Exception as install_exc:
            await playwright.stop()
            raise RuntimeError(
                "Playwright 브라우저 자동 복구에 실패했습니다. Render 빌드 명령과 네트워크 상태를 확인하세요."
            ) from install_exc

    context = await browser.new_context(
        viewport={"width": 500, "height": 812},
        screen={"width": 500, "height": 812},
        is_mobile=True,
        has_touch=True,
        device_scale_factor=1,
        permissions=["geolocation"],
        geolocation={"latitude": 37.5665, "longitude": 126.9780},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Mobile Safari/537.36"
        ),
        extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
    )
    await context.grant_permissions(["geolocation"], origin="https://go.hanpass.com")
    return playwright, browser, context, await context.new_page()


def import_scenario(path: Path):
    if str(SCENARIO_DIR.parent) not in sys.path:
        sys.path.insert(0, str(SCENARIO_DIR.parent))

    module_name = f"web_scenario_{path.stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"시나리오 로드 실패: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError(f"run(page) 함수 없음: {path.name}")
    return module
