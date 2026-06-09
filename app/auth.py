from __future__ import annotations

import time

from itsdangerous import BadSignature, URLSafeSerializer
from fastapi.responses import Response

from app.config import (
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    VALIDATOR_PASSWORD,
    VALIDATOR_SESSION_MINUTES,
    VALIDATOR_SESSION_SECRET,
    VALIDATOR_USER,
)


AUTH_COOKIE = "gohanpass_web_validator_session"
AUTH_STORAGE_KEY = "gohanpass_web_validator_auth"
RUN_STATE_KEY = "gohanpass_web_validator_run_state"
AUTH_SALT = "gohanpass-web-validator-auth-v1"
CONSOLE_WINDOW_NAME = "qa-console-sso"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(VALIDATOR_SESSION_SECRET, salt=AUTH_SALT)


def build_session(user: str, mode: str, expires_at: int) -> dict[str, int | str]:
    return {
        "user": user,
        "mode": mode,
        "exp": expires_at,
    }


def create_manual_session(user: str) -> dict[str, int | str]:
    return build_session(
        user=user,
        mode="manual",
        expires_at=int(time.time()) + VALIDATOR_SESSION_MINUTES * 60,
    )


def verify_manual_credentials(username: str, password: str) -> bool:
    return username == VALIDATOR_USER and password == VALIDATOR_PASSWORD


def issue_auth_cookie(response: Response, session: dict[str, int | str]) -> None:
    max_age = max(0, int(session["exp"]) - int(time.time()))
    token = _serializer().dumps(session)
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        AUTH_COOKIE,
        path="/",
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
    )


def read_auth_session(cookie_value: str | None) -> tuple[dict[str, int | str] | None, str | None]:
    if not cookie_value:
        return None, None

    try:
        session = _serializer().loads(cookie_value)
    except BadSignature:
        return None, "invalid"

    if not isinstance(session, dict):
        return None, "invalid"

    expires_at = int(session.get("exp", 0))
    if expires_at <= int(time.time()):
        return None, "expired"

    if session.get("user") != VALIDATOR_USER:
        return None, "invalid"

    if session.get("mode") not in {"manual", "console"}:
        return None, "invalid"

    return session, None
