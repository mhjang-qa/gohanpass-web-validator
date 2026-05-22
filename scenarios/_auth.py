import asyncio

from playwright.async_api import Page


LOGIN_EMAIL = "hanpassqa5@gmail.com"
LOGIN_PASSWORD = "xptmxm123!"
BASE_URL = "https://go.hanpass.com"
WEB_SIGNIN_API = "https://app.hanpass.com/app/v1/member/web-signin"


async def log(message: str):
    try:
        logger = getattr(log, "logger", None)
        if logger:
            logger(message)
    except Exception:
        pass


async def capture_checkpoint(page: Page, label: str):
    snapshot = getattr(page, "gohanpass_capture_snapshot", None)
    if snapshot:
        await snapshot(label)


async def short_pause(seconds: float = 0.2):
    await asyncio.sleep(seconds)


async def save_auth_state(page: Page):
    path = getattr(page, "gohanpass_auth_state_path", None)
    if not path:
        return
    try:
        await page.context.storage_state(path=path)
        await log("🔐 로그인 세션 저장 완료")
    except Exception:
        pass


async def load_saved_auth(page: Page) -> dict:
    try:
        return await page.evaluate(
            """() => {
                try {
                    const root = JSON.parse(localStorage.getItem("persist:root") || "{}");
                    return root.auth ? JSON.parse(root.auth) : {};
                } catch (error) {
                    return {};
                }
            }"""
        )
    except Exception:
        return {}


async def has_saved_auth_session(page: Page) -> bool:
    auth = await load_saved_auth(page)
    return bool(
        auth.get("isAuthenticated")
        and auth.get("session")
        and auth.get("memberSeq")
    )


async def apply_web_signin_state(page: Page, response_data: dict):
    payload = response_data.get("data") if isinstance(response_data.get("data"), dict) else response_data
    session = payload.get("session")
    member_seq = payload.get("memberSeq")
    if not session or not member_seq:
        return

    await page.evaluate(
        """({ payload }) => {
            const root = JSON.parse(localStorage.getItem("persist:root") || "{}");
            const previousAuth = root.auth ? JSON.parse(root.auth) : {};
            root.auth = JSON.stringify({
                ...previousAuth,
                memberSeq: payload.memberSeq,
                session: payload.session,
                token: payload.token || payload.accessToken || previousAuth.token || null,
                user: payload.user || previousAuth.user || payload,
                isAuthenticated: true,
                verifyTrigger: false,
            });
            root._persist = root._persist || JSON.stringify({ version: -1, rehydrated: true });
            localStorage.setItem("persist:root", JSON.stringify(root));
        }""",
        {"payload": payload},
    )


async def login_email_visible(page: Page) -> bool:
    try:
        email = page.get_by_placeholder("이메일").first
        return await email.count() > 0 and await email.is_visible()
    except Exception:
        return False


async def login_entry_visible(page: Page) -> bool:
    candidates = [
        page.locator("h2", has_text="로그인하기").first,
        page.get_by_text("로그인하기", exact=True).first,
        page.get_by_text("로그인하기", exact=False).first,
    ]

    for locator in candidates:
        try:
            if await locator.count() > 0 and await locator.is_visible():
                return True
        except Exception:
            pass

    return False


async def wait_for_home_or_login(page: Page, timeout_seconds: float = 5):
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if await is_logged_in_home(page):
            return
        if await login_email_visible(page):
            return
        try:
            login_text = page.get_by_text("로그인하기", exact=False).first
            if await login_text.count() > 0 and await login_text.is_visible():
                return
        except Exception:
            pass
        await asyncio.sleep(0.2)


async def go_home_and_wait(page: Page, timeout_seconds: float = 5):
    await page.goto(BASE_URL, wait_until="commit", timeout=10000)
    await wait_for_home_or_login(page, timeout_seconds=timeout_seconds)


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
        await short_pause()


async def is_logged_in_home(page: Page) -> bool:
    if await has_login_required_popup(page):
        return False

    if await login_email_visible(page):
        return False

    if await has_saved_auth_session(page):
        return True

    if await login_entry_visible(page):
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
    locator = page.locator(selector)
    count = await locator.count()
    for idx in range(count):
        target = locator.nth(idx)
        try:
            if await target.is_visible():
                await target.click(timeout=3000)
                return
        except Exception:
            pass
    await locator.first.click(timeout=3000, force=True)


async def click_keypad_command(page: Page, command: str):
    command_map = {
        "shift": "#nfilter_shift_l, #nfilter_shift_u, #nfilter_shift_s",
        "backspace": "#nfilter_backspace",
        "renew": "#nfilter_renew",
        "special": "#nfilter_lower2special, #nfilter_upper2special",
        "char": "#nfilter_change_char",
        "clear": "#nfilter_clear",
        "enter": "#nfilter_enter",
        "close": "#nfilter_close",
    }

    if command not in command_map:
        raise RuntimeError(f"지원하지 않는 command: {command}")

    locator = page.locator(command_map[command])
    count = await locator.count()
    for idx in range(count):
        target = locator.nth(idx)
        try:
            if await target.is_visible():
                await target.click(timeout=3000)
                return
        except Exception:
            pass
    await locator.first.click(timeout=3000, force=True)


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

        await asyncio.sleep(0.12)

    try:
        await click_keypad_command(page, "enter")
        await short_pause()
    except Exception:
        try:
            await click_keypad_command(page, "close")
            await short_pause()
        except Exception:
            pass


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

    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        if await login_form_visible():
            return
        if await login_entry_visible(page):
            break
        await asyncio.sleep(0.2)

    async def click_login_entry_from_dom() -> bool:
        return await page.evaluate(
            """() => {
                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.visibility !== "hidden"
                        && style.display !== "none"
                        && rect.width > 0
                        && rect.height > 0;
                };

                const loginTitle = Array.from(document.querySelectorAll("h1,h2,h3,p,span,div"))
                    .find((node) => visible(node) && (node.textContent || "").trim().includes("로그인하기"));
                if (!loginTitle) return false;

                const clickableSelector = [
                    "button",
                    "a",
                    "[role='button']",
                    "[onclick]",
                    ".cursor-pointer",
                    "[class*='cursor-pointer']",
                ].join(",");

                let scope = loginTitle;
                for (let depth = 0; scope && depth < 8; depth += 1, scope = scope.parentElement) {
                    if (scope.matches && scope.matches(clickableSelector) && visible(scope)) {
                        scope.click();
                        return true;
                    }

                    const candidates = Array.from(scope.querySelectorAll(clickableSelector))
                        .filter(visible);
                    const titleRect = loginTitle.getBoundingClientRect();
                    const target = candidates.find((node) => {
                        const rect = node.getBoundingClientRect();
                        const nearVertically = rect.top >= titleRect.top - 24
                            && rect.top <= titleRect.bottom + 96;
                        const rightSide = rect.left >= titleRect.left;
                        return nearVertically && rightSide;
                    }) || candidates[0];

                    if (target) {
                        target.click();
                        return true;
                    }
                }

                const rect = loginTitle.getBoundingClientRect();
                const points = [
                    [rect.right + 24, rect.top + rect.height / 2],
                    [rect.left + rect.width / 2, rect.top + rect.height / 2],
                    [rect.right + 48, rect.top + rect.height / 2],
                ];
                for (const [x, y] of points) {
                    const target = document.elementFromPoint(x, y);
                    if (target && visible(target)) {
                        target.click();
                        return true;
                    }
                }

                return false;
            }"""
        )

    selectors = [
        "h2:has-text('로그인하기') ~ button",
        "div:has(> h2:has-text('로그인하기')) button",
        "section:has(h2:has-text('로그인하기')) button",
        "article:has(h2:has-text('로그인하기')) button",
        "li:has(h2:has-text('로그인하기')) button",
        "div:has(h2:has-text('로그인하기')) [role='button']",
        "div:has(h2:has-text('로그인하기')) button:has(img[src*='ico16-btn-arrow-right'])",
        "button:has(img[src*='ico16-btn-arrow-right-grayscale-05.svg'])",
        "button:has(img[src*='ico16-btn-arrow-right'])",
        "button:has-text('로그인하기')",
        "a:has-text('로그인하기')",
        "[role='button']:has-text('로그인하기')",
        ".cursor-pointer:has-text('로그인하기')",
    ]

    last_error = None
    for selector in selectors:
        try:
            target = page.locator(selector).first
            await target.wait_for(state="visible", timeout=2000)
            await target.click(timeout=8000, force=True)
            if await wait_for_login_form():
                return
        except Exception as e:
            last_error = e

    try:
        if await click_login_entry_from_dom():
            if await wait_for_login_form():
                return
    except Exception as e:
        last_error = e

    try:
        clicked = await page.locator("h2", has_text="로그인하기").first.evaluate(
            """node => {
                let scope = node;
                for (let depth = 0; scope && depth < 8; depth += 1, scope = scope.parentElement) {
                    const button = scope.querySelector("button, a, [role='button'], [onclick], .cursor-pointer, [class*='cursor-pointer']");
                    if (button) {
                        button.click();
                        return true;
                    }
                }
                return false;
            }""",
            timeout=8000,
        )
        if clicked and await wait_for_login_form():
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
            }""",
            timeout=8000,
        )
        if clicked and await wait_for_login_form():
            return
    except Exception as e:
        last_error = e

    try:
        login_text = page.get_by_text("로그인하기", exact=False).first
        if await login_text.count() > 0:
            box = await login_text.bounding_box()
            if box:
                await page.mouse.click(box["x"] + box["width"] + 42, box["y"] + box["height"] / 2)
                if await wait_for_login_form():
                    return
    except Exception as e:
        last_error = e

    if await login_form_visible():
        return

    raise RuntimeError(f"로그인 진입 버튼을 찾지 못했습니다: {last_error}")


async def open_password_form(page: Page):
    password_input = page.get_by_placeholder("비밀번호").first
    try:
        if await password_input.count() > 0 and await password_input.is_visible():
            return
    except Exception:
        pass

    await page.get_by_role("button", name="로그인", exact=True).click(timeout=3000)
    await password_input.wait_for(state="visible", timeout=5000)


async def perform_login(page: Page):
    if await has_login_required_popup(page):
        await log("🔐 로그인 필요 팝업 감지 - 자동 로그인 진행")
        await close_login_required_popup(page)
        await short_pause()

    if not page.url.startswith(BASE_URL):
        await page.goto(BASE_URL, wait_until="commit", timeout=10000)

    if await is_logged_in_home(page):
        return

    await close_login_required_popup(page)
    await open_login_form(page)
    await log("🔐 로그인 페이지 진입 확인")

    email_input = page.locator("input[placeholder='이메일']")
    await email_input.wait_for(state="visible", timeout=8000)
    await email_input.fill("")
    await email_input.fill(LOGIN_EMAIL)
    await short_pause()
    await log("🔐 로그인 이메일 입력 완료")
    await capture_checkpoint(page, "login_email_entered")

    await open_password_form(page)
    await page.get_by_placeholder("비밀번호").click(timeout=3000)
    await short_pause(0.3)
    await enter_password_by_keypad(page, LOGIN_PASSWORD)
    await short_pause(0.3)
    await log("🔐 로그인 비밀번호 입력 완료")
    await capture_checkpoint(page, "login_password_entered")

    confirm_candidates = [
        page.get_by_role("button", name="확인", exact=True),
        page.locator("button:has-text('확인')").first,
        page.get_by_role("button", name="로그인", exact=True),
        page.locator("button.bg-primary.text-white.w-full:has-text('로그인')"),
        page.locator("section button:has-text('로그인')").first,
    ]
    last_error = None
    for confirm_btn in confirm_candidates:
        try:
            if await confirm_btn.count() == 0:
                continue
            await confirm_btn.wait_for(state="visible", timeout=1000)
            try:
                if not await confirm_btn.is_enabled():
                    continue
            except Exception:
                pass
            async with page.expect_response(
                lambda response: WEB_SIGNIN_API in response.url,
                timeout=8000,
            ) as response_info:
                await confirm_btn.click(timeout=2500)
            response = await response_info.value
            response_data = None
            try:
                setattr(page, "gohanpass_web_signin_status", response.status)
                response_data = await response.json()
                setattr(page, "gohanpass_web_signin_json", response_data)
            except Exception:
                setattr(page, "gohanpass_web_signin_status", response.status)
                setattr(page, "gohanpass_web_signin_json", None)
            result_code = response_data.get("resultCode") if isinstance(response_data, dict) else None
            result_message = response_data.get("resultMessage") if isinstance(response_data, dict) else None
            await log(f"🔐 web-signin 응답 확인: status={response.status}, resultCode={result_code}, message={result_message}")
            if result_code not in ("0", 0):
                raise RuntimeError(f"web-signin 실패: {result_message or result_code or '응답 JSON 없음'}")
            if isinstance(response_data, dict):
                await apply_web_signin_state(page, response_data)
            await page.goto(BASE_URL, wait_until="commit", timeout=10000)
            try:
                await page.wait_for_selector("button[aria-label='select_region']", timeout=3500)
            except Exception:
                try:
                    await page.wait_for_selector("text=한국에서 뭐하지?", timeout=1500)
                except Exception:
                    await short_pause(0.3)
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(f"로그인 버튼 클릭 실패: {last_error}")


async def verify_authenticated(page: Page):
    if await has_login_required_popup(page):
        await log("🔐 로그인 필요 팝업 재감지 - 자동 로그인 재시도")
        await perform_login(page)

    if await login_email_visible(page):
        raise RuntimeError("로그인 입력 화면이 남아있습니다.")

    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        if await is_logged_in_home(page):
            return
        await asyncio.sleep(0.25)

    raise RuntimeError("로그인 완료 후 홈 화면을 확인하지 못했습니다.")


async def ensure_logged_in(page: Page):
    if not page.url.startswith(BASE_URL):
        await go_home_and_wait(page)

    if await has_login_required_popup(page):
        await log("🔐 로그인 필요 팝업 감지 - 자동 로그인 시작")
        await close_login_required_popup(page)
    elif await is_logged_in_home(page):
        await log("🔐 로그인 상태 확인 완료")
        await save_auth_state(page)
        return

    if await has_saved_auth_session(page):
        await log("🔐 저장된 로그인 세션 확인 - 홈 화면 재진입")
        await go_home_and_wait(page)
        await close_login_required_popup(page)
        if await is_logged_in_home(page):
            await log("🔐 로그인 세션 재사용 완료")
            await save_auth_state(page)
            return

    await log("🔐 로그인 상태 없음 - 자동 로그인 시작")
    await perform_login(page)
    await verify_authenticated(page)
    await save_auth_state(page)
    await log("🔐 자동 로그인 완료")
