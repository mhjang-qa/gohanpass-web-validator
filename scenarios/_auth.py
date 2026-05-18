import asyncio

from playwright.async_api import Page


LOGIN_EMAIL = "hanpassqa5@gmail.com"
LOGIN_PASSWORD = "xptmxm123!"
BASE_URL = "https://go.hanpass.com"


async def log(message: str):
    try:
        logger = getattr(log, "logger", None)
        if logger:
            logger(message)
    except Exception:
        pass


async def has_login_required_popup(page: Page) -> bool:
    popup = page.get_by_text("로그인 후 이용해주세요.", exact=False)
    try:
        return await popup.count() > 0 and await popup.first.is_visible()
    except Exception:
        return False


async def close_login_required_popup(page: Page):
    if not await has_login_required_popup(page):
        return

    close_btn = page.get_by_role("button", name="닫기")
    if await close_btn.count() > 0:
        await close_btn.first.click(timeout=3000)
        await asyncio.sleep(0.5)


async def is_logged_in_home(page: Page) -> bool:
    if await has_login_required_popup(page):
        return False

    if await page.get_by_placeholder("이메일").count() > 0:
        return False

    selectors = [
        'button:has(img[alt="결제"])',
        'button:has(img[alt="여행"])',
        'button:has(img[src*="icon_main_menu.svg"])',
        'button[aria-label="select_region"]',
        'text=한국에서 뭐하지?',
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass

    return False


async def click_keypad_char(page: Page, ch: str):
    selector = f"button[nfiltercode='{ch}']"
    await page.wait_for_selector(selector, timeout=5000)
    await page.locator(selector).first.click()


async def click_keypad_command(page: Page, command: str):
    command_map = {
        "shift": "#nfilter_shift_l, #nfilter_shift_u, #nfilter_shift_s",
        "backspace": "#nfilter_backspace",
        "renew": "#nfilter_renew",
        "special": "#nfilter_lower2special, #nfilter_upper2special",
        "char": "#nfilter_change_char",
        "clear": "#nfilter_clear",
    }

    if command not in command_map:
        raise RuntimeError(f"지원하지 않는 command: {command}")

    await page.locator(command_map[command]).first.click()


async def enter_password_by_keypad(page: Page, password: str):
    for ch in password:
        if ch.islower() or ch.isdigit() or ch == " ":
            await click_keypad_char(page, ch)
        elif ch.isupper():
            await click_keypad_command(page, "shift")
            await click_keypad_char(page, ch)
        elif ch in "!@#$%^&*()~-_=+|[]{};:,.?/<>":
            await click_keypad_command(page, "special")
            await click_keypad_char(page, ch)
            await click_keypad_command(page, "char")
        else:
            raise RuntimeError(f"지원하지 않는 문자: {ch}")

        await asyncio.sleep(0.2)


async def open_login_form(page: Page):
    async def login_form_visible() -> bool:
        try:
            email = page.get_by_placeholder("이메일")
            return await email.count() > 0 and await email.first.is_visible()
        except Exception:
            return False

    async def wait_for_login_form(timeout_ms: int = 2500) -> bool:
        try:
            await page.get_by_placeholder("이메일").first.wait_for(state="visible", timeout=timeout_ms)
            return True
        except Exception:
            return await login_form_visible()

    if await login_form_visible():
        return

    selectors = [
        "button:has-text('로그인하기')",
        "a:has-text('로그인하기')",
        "[role='button']:has-text('로그인하기')",
        ".cursor-pointer:has-text('로그인하기')",
        "text=로그인하기",
        "button:has(img[src*='ico16-btn-arrow-right-grayscale-05.svg'])",
        "button:has-text('로그인')",
        "text=로그인",
    ]

    last_error = None
    for selector in selectors:
        try:
            target = page.locator(selector).first
            if await target.count() == 0:
                continue
            await target.click(timeout=5000, force=True)
            if await wait_for_login_form():
                return
        except Exception as e:
            last_error = e

    try:
        login_text = page.get_by_text("로그인하기", exact=False).first
        if await login_text.count() > 0:
            box = await login_text.bounding_box()
            if box:
                await page.mouse.click(box["x"] + box["width"] + 28, box["y"] + box["height"] / 2)
                if await wait_for_login_form():
                    return
    except Exception as e:
        last_error = e

    try:
        clicked = await page.get_by_text("로그인하기", exact=False).first.evaluate(
            """node => {
                const clickable = node.closest("button, a, [role='button'], .cursor-pointer");
                if (clickable) {
                    clickable.click();
                    return true;
                }
                const rect = node.getBoundingClientRect();
                const target = document.elementFromPoint(rect.right + 24, rect.top + rect.height / 2);
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }"""
        )
        if clicked and await wait_for_login_form():
            return
    except Exception as e:
        last_error = e

    if await login_form_visible():
        return

    raise RuntimeError(f"로그인 진입 버튼을 찾지 못했습니다: {last_error}")


async def perform_login(page: Page):
    if await has_login_required_popup(page):
        await log("🔐 로그인 필요 팝업 감지 - 자동 로그인 진행")
        await close_login_required_popup(page)
        await asyncio.sleep(0.5)

    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(2)

    if await is_logged_in_home(page):
        return

    await close_login_required_popup(page)
    await open_login_form(page)

    email_input = page.locator("input[placeholder='이메일']")
    await email_input.wait_for(state="visible", timeout=8000)
    await email_input.fill("")
    await email_input.type(LOGIN_EMAIL, delay=60)
    await asyncio.sleep(0.8)

    await page.get_by_placeholder("비밀번호").click()
    await asyncio.sleep(0.8)
    await enter_password_by_keypad(page, LOGIN_PASSWORD)
    await asyncio.sleep(0.8)

    confirm_btn = page.locator("button.bg-primary.text-white.w-full:has-text('확인')")
    await confirm_btn.wait_for(state="visible", timeout=5000)
    await confirm_btn.click()
    await asyncio.sleep(4)


async def verify_authenticated(page: Page):
    if await has_login_required_popup(page):
        await log("🔐 로그인 필요 팝업 재감지 - 자동 로그인 재시도")
        await perform_login(page)

    if await page.get_by_placeholder("이메일").count() > 0:
        raise RuntimeError("로그인 입력 화면이 남아있습니다.")

    try:
        await page.wait_for_selector("button[aria-label='select_region']", timeout=5000)
    except Exception:
        await page.wait_for_selector("text=한국에서 뭐하지?", timeout=3000)


async def ensure_logged_in(page: Page):
    if await has_login_required_popup(page):
        await log("🔐 로그인 필요 팝업 감지 - 자동 로그인 시작")
        await close_login_required_popup(page)
    elif await is_logged_in_home(page):
        await log("🔐 로그인 상태 확인 완료")
        return

    await log("🔐 로그인 상태 없음 - 자동 로그인 시작")
    await perform_login(page)
    await verify_authenticated(page)
    await log("🔐 자동 로그인 완료")
