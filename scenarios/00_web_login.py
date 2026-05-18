import asyncio
from datetime import datetime
from pathlib import Path

from scenarios._auth import ensure_logged_in, has_login_required_popup, is_logged_in_home


scenario_name = Path(__file__).stem
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


async def run(page):
    result = []

    async def step(name, func):
        try:
            await func()
            result.append((name, "PASS"))
        except Exception as e:
            result.append((name, f"FAIL ({str(e)})"))

    async def open_url():
        await page.goto("https://go.hanpass.com", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

    async def login_flow():
        await ensure_logged_in(page)

    async def login_result_check():
        if await has_login_required_popup(page):
            raise Exception("로그인 후 이용해주세요 팝업이 남아있습니다.")

        if await page.get_by_placeholder("이메일").count() > 0:
            raise Exception("로그인 입력 화면이 남아있습니다.")

        if not await is_logged_in_home(page):
            try:
                await page.wait_for_selector("button[aria-label='select_region']", timeout=5000)
            except Exception:
                await page.wait_for_selector("text=한국에서 뭐하지?", timeout=3000)

        if not await is_logged_in_home(page):
            raise Exception("로그인 완료 후 홈 화면을 확인하지 못했습니다.")

    await step("open_url", open_url)
    await step("login_flow", login_flow)
    await step("login_result_check", login_result_check)

    try:
        await page.screenshot(
            path=f"output/{scenario_name}_{timestamp}.png",
            timeout=15000,
            animations="disabled",
            caret="hide",
        )
    except Exception:
        pass
    return result
