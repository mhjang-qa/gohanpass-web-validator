from __future__ import annotations

import json
import time
from html import escape

from itsdangerous import BadSignature, URLSafeSerializer

from app.auth import AUTH_STORAGE_KEY, CONSOLE_WINDOW_NAME, RUN_STATE_KEY, build_session
from app.config import QA_CONSOLE_ALLOWED_ORIGIN, QA_CONSOLE_SHARED_SECRET


SSO_SALT = "qa-console-sso-v1"
TARGET = "validator"


def validate_sso_token(token: str) -> tuple[dict | None, str | None]:
    if not token:
        return None, "missing"
    if not QA_CONSOLE_SHARED_SECRET:
        return None, "disabled"

    try:
        payload = URLSafeSerializer(QA_CONSOLE_SHARED_SECRET, salt=SSO_SALT).loads(token)
    except BadSignature:
        return None, "invalid"

    if not isinstance(payload, dict):
        return None, "invalid"
    if payload.get("source") != "qa-console":
        return None, "invalid"
    if payload.get("target") != TARGET:
        return None, "invalid"

    expires_at = int(payload.get("exp", 0))
    if expires_at <= int(time.time()):
        return None, "expired"

    return payload, None


def is_allowed_console_referer(referer: str | None) -> bool:
    if not referer:
        return False
    return referer.startswith(QA_CONSOLE_ALLOWED_ORIGIN)


def build_console_session(payload: dict) -> dict[str, int | str]:
    return build_session(
        user=str(payload.get("user", "qa")),
        mode="console",
        expires_at=int(payload["exp"]),
    )


def launch_success_html(session: dict[str, int | str]) -> str:
    session_json = json.dumps(session, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <title>QA Console SSO</title>
  </head>
  <body>
    <script>
      const auth = {session_json};
      try {{
        window.localStorage.setItem("{AUTH_STORAGE_KEY}", JSON.stringify(auth));
        window.sessionStorage.setItem("{AUTH_STORAGE_KEY}", JSON.stringify(auth));
      }} catch (_error) {{}}
      window.name = "{CONSOLE_WINDOW_NAME}";
      window.location.replace("/");
    </script>
  </body>
</html>"""


def launch_failure_html(reason: str) -> str:
    safe_reason = escape(reason or "invalid")
    return f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <title>QA Console SSO</title>
  </head>
  <body>
    <script>
      try {{
        window.localStorage.removeItem("{AUTH_STORAGE_KEY}");
        window.sessionStorage.removeItem("{AUTH_STORAGE_KEY}");
      }} catch (_error) {{}}
      window.location.replace("/?auth_error={safe_reason}");
    </script>
  </body>
</html>"""


def logout_cleanup_html() -> str:
    return f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <title>QA Console Logout</title>
  </head>
  <body>
    <script>
      try {{
        window.localStorage.removeItem("{AUTH_STORAGE_KEY}");
        window.sessionStorage.removeItem("{AUTH_STORAGE_KEY}");
        window.sessionStorage.removeItem("{RUN_STATE_KEY}");
      }} catch (_error) {{}}
      window.name = "";
      document.body.textContent = "logout";
    </script>
  </body>
</html>"""
