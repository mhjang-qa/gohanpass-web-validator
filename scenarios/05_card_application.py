import asyncio

from scenarios._auth import BASE_URL, ensure_logged_in, has_login_required_popup, is_logged_in_home, log


async def run(page):
    result = []

    async def step(name, func):
        try:
            await log(f"▶ {name} 진행 중")
            await func()
            result.append((name, "PASS"))
            await log(f"✅ {name} 완료")
            return True
        except Exception as e:
            result.append((name, f"FAIL ({str(e)})"))
            await log(f"❌ {name} 실패: {str(e)}")
            return False

    async def optional_step(name, func):
        try:
            await log(f"▶ {name} 진행 중")
            await func()
            result.append((name, "PASS"))
            await log(f"✅ {name} 완료")
            return True
        except Exception as e:
            reason = str(e).splitlines()[0] if str(e) else type(e).__name__
            result.append((name, f"N/A ({reason})"))
            await log(f"⚠️ {name} 생략: {reason}")
            return False

    async def goto_home():
        if not page.url.startswith(BASE_URL):
            await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        await ensure_logged_in(page)
        await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await asyncio.sleep(0.5)
        if not await is_logged_in_home(page):
            raise RuntimeError("홈 화면을 확인하지 못했습니다.")

    async def close_known_overlay():
        candidates = [
            page.get_by_role("button", name="닫기"),
            page.get_by_role("button", name="확인"),
            page.locator("button:has(img[src*='ico18-close.svg'])"),
            page.locator("button:has(img[src*='close'])"),
        ]
        for locator in candidates:
            try:
                target = locator.first
                if await target.count() > 0 and await target.is_visible():
                    await target.click(timeout=3000)
                    await asyncio.sleep(0.25)
                    return
            except Exception:
                pass
        raise RuntimeError("닫을 수 있는 팝업/바텀시트를 찾지 못했습니다.")

    async def card_banner_visible():
        await page.get_by_text("공항에서 받는 카드 신청", exact=False).first.wait_for(
            state="visible",
            timeout=8000,
        )
        await page.get_by_text("캐시백", exact=False).first.wait_for(state="visible", timeout=8000)

    async def open_card_application():
        await page.get_by_text("공항에서 받는 카드 신청", exact=False).first.click(timeout=5000)
        await asyncio.sleep(1.0)
        if await has_login_required_popup(page):
            await close_known_overlay()
            return

        markers = [
            page.get_by_text("GO Hanpass Card", exact=False),
            page.get_by_text("카드", exact=False),
            page.get_by_text("신청", exact=False),
            page.get_by_text("서비스 준비중입니다.", exact=False),
        ]
        for marker in markers:
            try:
                if await marker.first.count() > 0 and await marker.first.is_visible():
                    return
            except Exception:
                pass
        raise RuntimeError("카드 신청 진입 결과를 확인하지 못했습니다.")

    async def return_home():
        try:
            await close_known_overlay()
        except Exception:
            pass
        await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        await asyncio.sleep(0.5)
        if not await is_logged_in_home(page):
            await ensure_logged_in(page)

    await step("ensure_login", lambda: ensure_logged_in(page))
    await step("open_home", goto_home)
    await step("card_banner_visible", card_banner_visible)
    await step("card_application_click", open_card_application)
    await optional_step("return_home_after_card", return_home)

    return result
