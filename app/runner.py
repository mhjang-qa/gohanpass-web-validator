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
from PIL import Image, ImageStat

from app.config import DATA_DIR, HEADLESS, OUTPUT_DIR, SCENARIO_DIR, TIMEZONE
from app.notion import upload_to_notion
from app.scenarios import resolve_scenario_paths, scenario_type
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
    if upper.startswith("ERROR"):
        return "error"
    if upper.startswith(("NA", "N/A")):
        return "na"
    return "fail"


def normalize_result(raw_result) -> dict:
    if isinstance(raw_result, dict):
        item = {key: value for key, value in raw_result.items()}
        item.setdefault("name", item.get("endpoint", "api_check"))
        item.setdefault("status", item.get("result", "ERROR"))
        return item

    if isinstance(raw_result, (list, tuple)) and len(raw_result) >= 2:
        return {"name": str(raw_result[0]), "status": str(raw_result[1])}

    return {"name": "scenario_result", "status": f"ERROR (invalid result: {raw_result})"}


def create_run_record(
    scenario_names: list[str],
    source: str,
    run_id: str | None = None,
    snapshot_interval_seconds: int = 30,
) -> tuple[dict, list[Path]]:
    run_id = run_id or datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y%m%d_%H%M%S")
    scenario_paths = resolve_scenario_paths(scenario_names)
    run = {
        "id": run_id,
        "source": source,
        "requested_scenarios": scenario_names,
        "status": "running",
        "started_at": now_iso(),
        "finished_at": None,
        "scenarios": [],
        "summary": {"total": 0, "pass": 0, "fail": 0, "na": 0, "error": 0},
        "logs": [],
        "snapshots": [],
        "attachments": [],
        "notion": None,
        "snapshot_interval_seconds": max(10, int(snapshot_interval_seconds or 30)),
        "progress": {
            "percent": 0,
            "label": "실행 대기 중",
            "current": 0,
            "total": len(scenario_paths),
        },
    }
    save_run(run)
    return run, scenario_paths


def append_run_log(run: dict, message: str):
    run["logs"].append(message)
    save_run(run)


def update_run_progress(run: dict, percent: int, label: str, current: int | None = None) -> None:
    progress = run.setdefault("progress", {})
    progress["percent"] = max(0, min(100, int(percent)))
    progress["label"] = label
    progress["total"] = len(run.get("requested_scenarios", []))
    if current is not None:
        progress["current"] = current
    save_run(run)


async def capture_snapshot(run: dict, page, label: str = "live") -> None:
    snapshot_dir = OUTPUT_DIR / run["id"] / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H%M%S")
    filename = f"{label}_{len(run['snapshots']) + 1:03d}_{timestamp}.png"
    file_path = snapshot_dir / filename
    try:
        await page.screenshot(
            path=str(file_path),
            full_page=False,
            timeout=2500,
            animations="disabled",
            caret="hide",
        )
        if not _is_meaningful_snapshot(file_path):
            if file_path.exists():
                file_path.unlink(missing_ok=True)
            if not run["snapshots"]:
                append_run_log(run, "📸 스냅샷 생략: 화면이 아직 준비되지 않았습니다.")
            return

        snapshot_ref = f"/output/{run['id']}/snapshots/{filename}"
        run["snapshots"].append(snapshot_ref)
        active_name = run.get("current_scenario_name")
        if active_name:
            for scenario in run.get("scenarios", []):
                if scenario.get("name") == active_name:
                    scenario.setdefault("snapshots", []).append(snapshot_ref)
                    break
        save_run(run)
        append_run_log(run, f"📸 스냅샷 저장: {filename}")
    except Exception as exc:
        message = str(exc)
        if "Timeout" in message:
            append_run_log(run, "📸 스냅샷 생략: 캡처 타임아웃")
        else:
            append_run_log(run, f"📸 스냅샷 생략: {message.splitlines()[0]}")


def bind_scenario_snapshot(run: dict, page):
    async def scenario_snapshot(label: str):
        await capture_snapshot(run, page, label=label)

    setattr(page, "gohanpass_capture_snapshot", scenario_snapshot)


async def snapshot_loop(run: dict, page, stop_event: asyncio.Event) -> None:
    interval = max(10, int(run.get("snapshot_interval_seconds", 30) or 30))
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            if stop_event.is_set():
                break
            await capture_snapshot(run, page)


def _is_meaningful_snapshot(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            sample = image.convert("L").resize((64, 64))
            stat = ImageStat.Stat(sample)
            return stat.stddev[0] >= 8.0
    except Exception:
        return True


async def execute_run(run: dict, scenario_paths: list[Path], notion_upload: bool = True) -> dict:
    global CURRENT_RUN_ID

    CURRENT_RUN_ID = run["id"]
    playwright = browser = context = page = None
    snapshot_stop = asyncio.Event()
    snapshot_task: asyncio.Task | None = None
    try:
        scenario_count = max(1, len(scenario_paths))
        update_run_progress(run, 5, "실행 환경 준비 중", 0)
        append_run_log(run, "⏳ 실행 환경 준비 중")
        for idx, path in enumerate(scenario_paths, 1):
            scenario_start_percent = 10 + int(((idx - 1) / scenario_count) * 70)
            update_run_progress(run, scenario_start_percent, f"{path.name} 실행 준비 중", idx)
            append_run_log(run, f"[{idx}/{len(scenario_paths)}] {path.name} 시작")
            current_type = scenario_type(path)
            scenario_result = {"name": path.name, "type": current_type, "results": [], "snapshots": []}
            run["scenarios"].append(scenario_result)
            run["current_scenario_name"] = path.name
            save_run(run)
            try:
                module = import_scenario(path)
                if hasattr(module, "log"):
                    module.log.logger = lambda message: append_run_log(run, message)
                auth_module = sys.modules.get("scenarios._auth")
                if auth_module and hasattr(auth_module, "log"):
                    auth_module.log.logger = lambda message: append_run_log(run, message)

                module_type = getattr(module, "SCENARIO_TYPE", current_type)
                scenario_result["type"] = module_type
                if module_type == "api":
                    update_run_progress(run, scenario_start_percent + 8, f"{path.name} API 검증 실행 중", idx)
                    raw_results = await module.run()
                else:
                    if page is None:
                        update_run_progress(run, scenario_start_percent + 5, "브라우저 실행 및 모바일 컨텍스트 준비 중", idx)
                        append_run_log(run, "🌐 브라우저 실행 및 모바일 컨텍스트 준비 중")
                        playwright, browser, context, page = await create_page()
                        bind_scenario_snapshot(run, page)
                        snapshot_task = asyncio.create_task(snapshot_loop(run, page, snapshot_stop))
                        append_run_log(run, "🌐 브라우저 준비 완료")
                    update_run_progress(run, scenario_start_percent + 12, f"{path.name} 시나리오 단계 실행 중", idx)
                    raw_results = await module.run(page)
            except Exception as exc:
                raw_results = [("scenario_execution", f"FAIL ({exc})")]
                append_run_log(run, f"{path.name} 실패: {exc}")

            for raw_result in raw_results:
                item = normalize_result(raw_result)
                status = str(item.get("status", "ERROR"))
                kind = classify_status(status)
                run["summary"]["total"] += 1
                run["summary"][kind] += 1
                scenario_result["results"].append(item)

            if page is not None and scenario_result["type"] != "api" and not scenario_result["snapshots"]:
                update_run_progress(run, scenario_start_percent + 60, f"{path.name} 최종 화면 캡처 중", idx)
                await capture_snapshot(run, page, label=f"{path.stem}_final")
            run["current_scenario_name"] = None
            scenario_done_percent = 10 + int((idx / scenario_count) * 70)
            update_run_progress(run, scenario_done_percent, f"{path.name} 결과 정리 완료", idx)
            append_run_log(run, f"[{idx}/{len(scenario_paths)}] {path.name} 완료")
            save_run(run)

        if page is not None:
            update_run_progress(run, 84, "최종 스크린샷 저장 중", len(scenario_paths))
            append_run_log(run, "📸 최종 스크린샷 저장 중")
            screenshot_path = OUTPUT_DIR / f"{run['id']}.png"
            try:
                await page.screenshot(
                    path=str(screenshot_path),
                    full_page=False,
                    timeout=5000,
                    animations="disabled",
                    caret="hide",
                )
            except Exception as exc:
                append_run_log(run, f"📸 최종 스크린샷 생략: {str(exc).splitlines()[0]}")

        update_run_progress(run, 88, "실행 로그 파일 저장 중", len(scenario_paths))
        log_path = OUTPUT_DIR / f"{run['id']}.txt"
        log_path.write_text("\n".join(run["logs"]), encoding="utf-8")
        run["log_path"] = str(log_path)

        if notion_upload:
            update_run_progress(run, 92, "Notion 리포트 등록 중", len(scenario_paths))
            append_run_log(run, "📝 Notion 리포트 등록 중")
            notion_result = upload_to_notion(run)
            run["notion"] = {"uploaded": True, "page_id": notion_result.get("id") if notion_result else None}
            append_run_log(run, "📝 Notion 리포트 등록 완료")

        run["status"] = "completed" if run["summary"]["fail"] == 0 and run["summary"].get("error", 0) == 0 else "failed"
        update_run_progress(run, 100, "실행 완료", len(scenario_paths))
        return run
    except Exception as exc:
        run["status"] = "failed"
        update_run_progress(run, 100, "실행 오류 발생", len(scenario_paths))
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


async def run_scenarios(
    scenario_names: list[str],
    notion_upload: bool = True,
    source: str = "manual",
    run_id: str | None = None,
    snapshot_interval_seconds: int = 30,
) -> dict:
    if RUN_LOCK.locked() or any(not task.done() for task in RUN_TASKS.values()):
        raise RuntimeError("이미 실행 중인 작업이 있습니다.")

    async with RUN_LOCK:
        run, scenario_paths = create_run_record(
            scenario_names,
            source,
            run_id=run_id,
            snapshot_interval_seconds=snapshot_interval_seconds,
        )
        return await execute_run(run, scenario_paths, notion_upload=notion_upload)


def start_run_scenarios(
    scenario_names: list[str],
    notion_upload: bool = True,
    source: str = "manual",
    run_id: str | None = None,
    snapshot_interval_seconds: int = 30,
) -> dict:
    if RUN_LOCK.locked() or any(not task.done() for task in RUN_TASKS.values()):
        raise RuntimeError("이미 실행 중인 작업이 있습니다.")

    run, scenario_paths = create_run_record(
        scenario_names,
        source,
        run_id=run_id,
        snapshot_interval_seconds=snapshot_interval_seconds,
    )
    task = asyncio.create_task(
        run_scenarios_background(
            run,
            scenario_paths,
            notion_upload=notion_upload,
        )
    )
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

    auth_state_path = DATA_DIR / "web_auth_state.json"
    context_options = {
        "viewport": {"width": 500, "height": 812},
        "screen": {"width": 500, "height": 812},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 1,
        "permissions": ["geolocation"],
        "geolocation": {"latitude": 37.5665, "longitude": 126.9780},
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Mobile Safari/537.36"
        ),
        "extra_http_headers": {"Accept-Language": "ko-KR,ko;q=0.9"},
    }
    if auth_state_path.exists():
        context_options["storage_state"] = str(auth_state_path)

    context = await browser.new_context(**context_options)
    await context.grant_permissions(["geolocation"], origin="https://go.hanpass.com")
    page = await context.new_page()
    setattr(page, "gohanpass_auth_state_path", str(auth_state_path))
    return playwright, browser, context, page


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
