import asyncio

from scenarios._auth import BASE_URL, ensure_logged_in, is_logged_in_home, log


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

    async def wait_home(timeout_seconds: float = 8):
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if await is_logged_in_home(page):
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("홈 화면을 확인하지 못했습니다.")

    async def goto_home():
        if not page.url.startswith(BASE_URL):
            await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        await ensure_logged_in(page)
        if not await is_logged_in_home(page):
            await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        await wait_home()
        await page.wait_for_load_state("domcontentloaded", timeout=10000)

    async def click_visible(locator, timeout=8000):
        target = locator.first
        await target.wait_for(state="visible", timeout=timeout)
        try:
            await target.click(timeout=2500)
            return
        except Exception:
            pass
        try:
            await target.click(timeout=2500, force=True)
            return
        except Exception:
            pass
        await target.evaluate("el => el.click()")

    async def close_overlay():
        candidates = [
            page.get_by_role("button", name="닫기"),
            page.get_by_role("button", name="확인"),
            page.locator("button:has(img[src*='ico18-close.svg'])"),
            page.locator("button:has(img[src*='ico24-close.svg'])"),
        ]
        for locator in candidates:
            try:
                if await locator.count() == 0:
                    continue
                await click_visible(locator, timeout=1500)
                await asyncio.sleep(0.2)
                return
            except Exception:
                pass
        raise RuntimeError("닫을 수 있는 팝업/바텀시트를 찾지 못했습니다.")

    async def click_back():
        candidates = [
            page.locator("button:has(img[src*='ico24-back.svg'])"),
            page.locator("button:has(img[src*='ico16-btn-arrow-left.svg'])"),
            page.get_by_role("button", name="뒤로가기"),
            page.get_by_role("button", name="이전"),
        ]
        for locator in candidates:
            try:
                if await locator.count() == 0:
                    continue
                await click_visible(locator, timeout=1500)
                await asyncio.sleep(0.2)
                return
            except Exception:
                pass
        await page.go_back(wait_until="commit", timeout=7000)

    async def scroll_down():
        for _ in range(3):
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(0.08)

    async def scroll_up():
        for _ in range(2):
            await page.mouse.wheel(0, -800)
            await asyncio.sleep(0.08)

    async def select_region(region_name: str):
        await click_visible(page.locator("button[aria-label='select_region']"))
        await click_visible(page.get_by_text(region_name, exact=True))
        await asyncio.sleep(0.2)

    async def open_weather():
        candidates = [
            page.locator("button:has-text('℃')"),
            page.locator("button:has-text('°C')"),
        ]
        for locator in candidates:
            try:
                if await locator.count() == 0:
                    continue
                await click_visible(locator)
                return
            except Exception:
                pass
        raise RuntimeError("날씨 진입 버튼을 찾지 못했습니다.")

    async def open_menu():
        await click_visible(page.locator("button:has(img[src*='icon_main_menu.svg'])"))

    async def swipe_banner(delta: int):
        banner = page.locator("div.overflow-x-auto.scroll-hidden").first
        await banner.wait_for(state="visible", timeout=5000)
        await banner.evaluate(
            "(el, left) => el.scrollBy({ left, behavior: 'instant' })",
            delta,
        )
        await asyncio.sleep(0.2)

    async def click_image_button(image_name: str):
        await click_visible(page.locator(f"button:has(img[src*='{image_name}'])"))

    await step("ensure_login", lambda: ensure_logged_in(page))
    await step("open_home", goto_home)

    await step("region_open_click", lambda: click_visible(page.locator("button[aria-label='select_region']")))
    await optional_step("region_close_click", close_overlay)

    if await step("weather_click", open_weather):
        await step("scroll_down", scroll_down)
        await step("scroll_up", scroll_up)
        for region in ["서울", "인천", "부산"]:
            await optional_step(f"select_region_{region}", lambda r=region: select_region(r))
        await optional_step("back_click", click_back)

    await step("return_home_after_weather", goto_home)

    if await optional_step("menu_open_click", open_menu):
        await step("menu_scroll_down", scroll_down)
        await step("menu_scroll_up", scroll_up)
        await optional_step("Customer_Service_open_click", lambda: click_image_button("ico24_headphones.svg"))
        await optional_step("Customer_Service_back_click", click_back)
        await optional_step("push_noti_click", lambda: click_image_button("ico20-caution-light-gray.svg"))
        await optional_step("push_noti_back_click", click_back)
        await optional_step("wallet_info_click", lambda: click_image_button("ico16-line-info.svg"))
        await optional_step("wallet_info_close_click", close_overlay)

    await step("return_home_after_menu", goto_home)
    await step("main_scroll_down", scroll_down)
    await optional_step("banner_swipe_right", lambda: swipe_banner(220))
    await optional_step("banner_swipe_left", lambda: swipe_banner(-220))

    for name, image in [
        ("Top_Up_Transit_Card_click", "transport-img-01@4x.png"),
        ("taxi_click", "transport-img-02@4x.png"),
        ("bus_click", "transport-img-04@4x.png"),
    ]:
        if await optional_step(name, lambda img=image: click_image_button(img)):
            await optional_step(f"{name}_close_or_back", close_overlay)
            await optional_step(f"{name}_back", click_back)
            await goto_home()
            await step(f"return_home_after_{name}", goto_home)
            await step("main_scroll_down", scroll_down)

    await optional_step("travel_content_more_click", page.get_by_role("button", name="여행 컨텐츠 더보기").click)
    await optional_step("BS_closed_click", close_overlay)

    async def check_home_success():
        await goto_home()
        if not await is_logged_in_home(page):
            raise RuntimeError("홈 화면 복귀 상태 확인 실패")

    await step("home_result_check", check_home_success)

    return result
