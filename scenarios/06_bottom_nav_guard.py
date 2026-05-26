import asyncio

from scenarios._auth import BASE_URL, ensure_logged_in, log, reauthenticate_if_required, wait_for_authenticated_home


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

    async def goto_home():
        if not page.url.startswith(BASE_URL):
            await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        await ensure_logged_in(page)
        await page.goto(f"{BASE_URL}/home", wait_until="commit", timeout=10000)
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await wait_for_authenticated_home(page)

    async def login_if_required():
        return await reauthenticate_if_required(page)

    async def click_bottom_nav(alt_text: str):
        target = page.locator(f"div.fixed.bottom-0 button:has(img[alt='{alt_text}'])").last
        if await target.count() == 0:
            target = page.locator(f"button:has(img[alt='{alt_text}'])").last
        await target.wait_for(state="visible", timeout=8000)
        try:
            await target.click(timeout=3000)
        except Exception:
            await target.click(timeout=3000, force=True)
        await asyncio.sleep(0.8)

    async def assert_controlled_response(markers):
        if await login_if_required():
            return
        for locator in markers:
            try:
                target = locator.first
                if await target.count() > 0 and await target.is_visible():
                    return
            except Exception:
                pass
        raise RuntimeError("탭 진입 결과 또는 보호 팝업을 확인하지 못했습니다.")

    async def home_tab_check():
        await goto_home()
        await click_bottom_nav("홈")
        await wait_for_authenticated_home(page)

    async def travel_tab_check():
        await goto_home()
        await click_bottom_nav("여행")
        await assert_controlled_response([
            page.locator("input[placeholder='어디로 갈까요?']"),
            page.get_by_text("어디로 갈까요?", exact=False),
            page.get_by_text("예약내역 보기", exact=False),
            page.get_by_text("약국", exact=True),
        ])

    async def payment_tab_check():
        await goto_home()
        await click_bottom_nav("결제")
        await assert_controlled_response([
            page.get_by_text("충전", exact=True),
            page.get_by_text("출금", exact=True),
            page.get_by_text("송금", exact=True),
            page.get_by_text("GO Hanpass Card", exact=False),
        ])

    async def my_page_tab_check():
        await goto_home()
        await click_bottom_nav("my_page")
        await assert_controlled_response([
            page.get_by_text("마이", exact=False),
            page.get_by_text("MY", exact=False),
            page.get_by_text("회원", exact=False),
            page.get_by_text("로그아웃", exact=False),
        ])

    await step("ensure_login", lambda: ensure_logged_in(page))
    await step("open_home", goto_home)
    await step("home_tab_check", home_tab_check)
    await step("travel_tab_check", travel_tab_check)
    await step("payment_tab_guard_or_page_check", payment_tab_check)
    await step("my_page_guard_or_page_check", my_page_tab_check)

    return result
