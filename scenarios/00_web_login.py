import asyncio
from time import perf_counter

from scenarios._auth import BASE_URL, ensure_logged_in, has_login_required_popup, is_logged_in_home, log


async def run(page):
    result = []

    async def step(name, func):
        started = perf_counter()
        try:
            await log(f"▶ {name} 진행 중")
            await func()
            result.append((name, "PASS"))
            await log(f"✅ {name} 완료 ({perf_counter() - started:.1f}s)")
            return True
        except Exception as e:
            result.append((name, f"FAIL ({str(e)})"))
            await log(f"❌ {name} 실패 ({perf_counter() - started:.1f}s): {str(e)}")
            return False

    async def open_url():
        await log("🌐 GO Hanpass 홈 접속 중")
        if not page.url.startswith(BASE_URL):
            await page.goto(BASE_URL, wait_until="commit", timeout=10000)
        settled_until = perf_counter() + 5
        while perf_counter() < settled_until:
            if await is_logged_in_home(page):
                return
            try:
                login_text = page.get_by_text("로그인하기", exact=False).first
                if await login_text.count() > 0 and await login_text.is_visible():
                    return
            except Exception:
                pass
            if await page.get_by_placeholder("이메일").count() > 0:
                return
            await asyncio.sleep(0.2)

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

    async def web_signin_response_check():
        data = getattr(page, "gohanpass_web_signin_json", None)
        status = getattr(page, "gohanpass_web_signin_status", None)
        if not isinstance(data, dict):
            if await is_logged_in_home(page):
                await log("🔐 기존 로그인 세션 사용 - web-signin 응답 검증 생략")
                return
            raise Exception(f"web-signin 응답 JSON 없음(status={status})")

        if data.get("resultCode") != "0":
            raise Exception(f"resultCode={data.get('resultCode')}")
        if data.get("resultMessage") != "SUCCESS":
            raise Exception(f"resultMessage={data.get('resultMessage')}")

        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        if not payload.get("session"):
            raise Exception("session 값 없음")
        if not payload.get("memberSeq"):
            raise Exception("memberSeq 값 없음")

    if not await step("open_url", open_url):
        result.append(("login_flow", "FAIL (URL 접속 실패로 로그인 중단)"))
        result.append(("login_result_check", "FAIL (URL 접속 실패로 검증 중단)"))
        return result

    if not await step("login_flow", login_flow):
        result.append(("web_signin_response_check", "FAIL (로그인 플로우 실패로 검증 중단)"))
        result.append(("login_result_check", "FAIL (로그인 플로우 실패로 검증 중단)"))
        return result

    await step("web_signin_response_check", web_signin_response_check)
    await step("login_result_check", login_result_check)

    return result
