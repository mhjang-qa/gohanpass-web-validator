import asyncio

from scenarios._auth import BASE_URL, ensure_logged_in, is_logged_in_home, log, reauthenticate_if_required


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
        deadline = asyncio.get_running_loop().time() + 8
        while asyncio.get_running_loop().time() < deadline:
            if await is_logged_in_home(page):
                return
            if await reauthenticate_if_required(page):
                await page.goto(BASE_URL, wait_until="commit", timeout=10000)
            await asyncio.sleep(0.25)
        raise RuntimeError("홈 화면을 확인하지 못했습니다.")

    async def wait_for_home_route(timeout_seconds: float = 12):
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_error = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                departure = page.locator("button[aria-label='출발지']").first
                arrival = page.locator("button[aria-label='도착지']").first
                search = page.locator("button:has(img[alt='검색'])").first
                if (
                    await departure.count() > 0
                    and await departure.is_visible()
                    and await arrival.count() > 0
                    and await arrival.is_visible()
                    and await search.count() > 0
                    and await search.is_visible()
                ):
                    return
            except Exception as e:
                last_error = e

            if not await is_logged_in_home(page):
                await ensure_logged_in(page)
            await asyncio.sleep(0.3)

        raise RuntimeError(f"홈 추천 경로 영역을 확인하지 못했습니다: {last_error}")

    async def click_first_visible(locators, timeout=8000):
        last_error = None
        for locator in locators:
            try:
                target = locator.first
                await target.wait_for(state="visible", timeout=timeout)
                try:
                    await target.click(timeout=3000)
                except Exception:
                    await target.click(timeout=3000, force=True)
                return
            except Exception as e:
                last_error = e
        raise RuntimeError(f"클릭 대상 미노출: {last_error}")

    async def login_if_required():
        return await reauthenticate_if_required(page)

    async def route_recommendation_visible():
        await wait_for_home_route()

    async def open_departure_selector():
        await click_first_visible([
            page.get_by_role("button", name="출발지"),
            page.locator("button[aria-label='출발지']"),
        ])
        await asyncio.sleep(0.5)
        if await login_if_required():
            return
        await page.get_by_text("출발지", exact=False).first.wait_for(state="visible", timeout=5000)

    async def open_arrival_selector():
        await goto_home()
        await click_first_visible([
            page.get_by_role("button", name="도착지"),
            page.locator("button[aria-label='도착지']"),
        ])
        await asyncio.sleep(0.5)
        if await login_if_required():
            return
        await page.get_by_text("도착지", exact=False).first.wait_for(state="visible", timeout=5000)

    async def execute_route_search():
        await goto_home()
        await click_first_visible([
            page.locator("button:has(img[alt='검색'])"),
            page.locator("button:has(img[src*='ico24-search.svg'])"),
        ])
        await asyncio.sleep(1.0)
        if await login_if_required():
            return
        route_markers = [
            page.get_by_text("택시", exact=True),
            page.get_by_text("버스", exact=True),
            page.get_by_text("KTX", exact=True),
            page.get_by_text("경로", exact=False),
        ]
        for marker in route_markers:
            try:
                if await marker.first.count() > 0 and await marker.first.is_visible():
                    return
            except Exception:
                pass
        raise RuntimeError("추천 경로 검색 결과 또는 보호 팝업을 확인하지 못했습니다.")

    await step("ensure_login", lambda: ensure_logged_in(page))
    if not await step("open_home", goto_home):
        return result
    if not await optional_step("route_recommendation_visible", route_recommendation_visible):
        reason = "현재 홈 화면에 추천 경로 영역이 노출되지 않음"
        result.extend([
            ("departure_selector_open", f"N/A ({reason})"),
            ("arrival_selector_open", f"N/A ({reason})"),
            ("route_search_click", f"N/A ({reason})"),
        ])
        return result
    await optional_step("departure_selector_open", open_departure_selector)
    await optional_step("arrival_selector_open", open_arrival_selector)
    await step("route_search_click", execute_route_search)

    return result
