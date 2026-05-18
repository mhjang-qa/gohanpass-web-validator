import asyncio
import importlib.util
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

from app.config import HEADLESS, MOBILE_VALIDATOR_DIR, OUTPUT_DIR, SCENARIO_DIR, TIMEZONE
from app.notion import upload_to_notion
from app.scenarios import resolve_scenario_paths
from app.storage import save_run


RUN_LOCK = asyncio.Lock()


def now_iso() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")


def classify_status(status: str) -> str:
    upper = str(status).upper()
    if upper.startswith("PASS"):
        return "pass"
    if upper.startswith(("NA", "N/A")):
        return "na"
    return "fail"


async def create_page():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=HEADLESS,
        args=[
            "--window-size=500,920",
            "--force-device-scale-factor=1",
            "--disable-features=TranslateUI",
            "--lang=ko-KR",
            "--disable-translate",
            "--no-first-run",
        ],
    )
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
    if str(MOBILE_VALIDATOR_DIR) not in sys.path:
        sys.path.insert(0, str(MOBILE_VALIDATOR_DIR))

    module_name = f"web_scenario_{path.stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"시나리오 로드 실패: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError(f"run(page) 함수 없음: {path.name}")
    return module


async def run_scenarios(scenario_names: list[str], notion_upload: bool = True, source: str = "manual") -> dict:
    if RUN_LOCK.locked():
        raise RuntimeError("이미 실행 중인 작업이 있습니다.")

    async with RUN_LOCK:
        run_id = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y%m%d_%H%M%S")
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
            "attachments": [],
            "notion": None,
        }
        save_run(run)

        playwright = browser = context = page = None
        try:
            playwright, browser, context, page = await create_page()
            for idx, path in enumerate(scenario_paths, 1):
                run["logs"].append(f"[{idx}/{len(scenario_paths)}] {path.name} 시작")
                scenario_result = {"name": path.name, "results": []}
                try:
                    module = import_scenario(path)
                    if hasattr(module, "log"):
                        module.log.logger = run["logs"].append
                    auth_module = sys.modules.get("scenarios._auth")
                    if auth_module and hasattr(auth_module, "log"):
                        auth_module.log.logger = run["logs"].append

                    raw_results = await module.run(page)
                except Exception as exc:
                    raw_results = [("scenario_execution", f"FAIL ({exc})")]
                    run["logs"].append(f"{path.name} 실패: {exc}")

                for name, status in raw_results:
                    kind = classify_status(status)
                    run["summary"]["total"] += 1
                    run["summary"][kind] += 1
                    scenario_result["results"].append({"name": str(name), "status": str(status)})

                run["scenarios"].append(scenario_result)
                save_run(run)

            screenshot_path = OUTPUT_DIR / f"{run_id}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            run["attachments"].append(str(screenshot_path))

            log_path = OUTPUT_DIR / f"{run_id}.log"
            log_path.write_text("\n".join(run["logs"]), encoding="utf-8")
            run["attachments"].append(str(log_path))

            if notion_upload:
                notion_result = upload_to_notion(run)
                run["notion"] = {"uploaded": True, "page_id": notion_result.get("id") if notion_result else None}

            run["status"] = "completed" if run["summary"]["fail"] == 0 else "failed"
            return run
        except Exception as exc:
            run["status"] = "failed"
            run["logs"].append(f"실행 오류: {exc}")
            return run
        finally:
            run["finished_at"] = now_iso()
            save_run(run)
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
