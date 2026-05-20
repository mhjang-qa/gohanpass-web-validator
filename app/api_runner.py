import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests

from app.config import API_BASE_URL, API_HEADERS, API_TIMEOUT_SECONDS, API_TOKEN


@dataclass(frozen=True)
class ApiCheck:
    name: str
    method: str
    endpoint: str
    expected_status: int | None = None
    headers: dict[str, str] | None = None
    params: dict[str, Any] | None = None
    json_body: dict[str, Any] | None = None


def load_api_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    if API_HEADERS:
        try:
            extra_headers = json.loads(API_HEADERS)
        except json.JSONDecodeError as exc:
            raise RuntimeError("API_HEADERS는 JSON object 형식이어야 합니다.") from exc
        if not isinstance(extra_headers, dict):
            raise RuntimeError("API_HEADERS는 JSON object 형식이어야 합니다.")
        headers.update({str(key): str(value) for key, value in extra_headers.items()})

    return headers


def classify_api_status(status_code: int, expected_status: int | None = None) -> tuple[str, str]:
    if expected_status is not None and status_code != expected_status:
        return "FAIL", f"expected status {expected_status}, got {status_code}"
    if status_code == 200:
        return "PASS", "status code 200"
    if status_code == 400:
        return "FAIL", "status code 400"
    if status_code in (401, 403):
        return "ERROR", f"authorization error status {status_code}"
    if status_code == 404:
        return "FAIL", "endpoint not found status 404"
    if 500 <= status_code:
        return "ERROR", f"server error status {status_code}"
    if 400 <= status_code:
        return "FAIL", f"client error status {status_code}"
    return "ERROR", f"unexpected status {status_code}"


def _request(check: ApiCheck) -> dict[str, Any]:
    headers = load_api_headers()
    headers.update(check.headers or {})
    url = urljoin(f"{API_BASE_URL}/", check.endpoint.lstrip("/"))
    response = requests.request(
        check.method.upper(),
        url,
        headers=headers,
        params=check.params,
        json=check.json_body,
        timeout=API_TIMEOUT_SECONDS,
    )
    result, reason = classify_api_status(response.status_code, check.expected_status)
    return {
        "name": check.name,
        "type": "api",
        "method": check.method.upper(),
        "endpoint": check.endpoint,
        "status_code": response.status_code,
        "result": result,
        "status": result if result == "PASS" else f"{result} ({reason})",
        "reason": "" if result == "PASS" else reason,
    }


async def run_api_checks(checks: list[ApiCheck]) -> list[dict[str, Any]]:
    results = []
    for check in checks:
        try:
            results.append(await asyncio.to_thread(_request, check))
        except requests.Timeout:
            results.append(
                {
                    "name": check.name,
                    "type": "api",
                    "method": check.method.upper(),
                    "endpoint": check.endpoint,
                    "status_code": None,
                    "result": "ERROR",
                    "status": "ERROR (request timeout)",
                    "reason": "request timeout",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "name": check.name,
                    "type": "api",
                    "method": check.method.upper(),
                    "endpoint": check.endpoint,
                    "status_code": None,
                    "result": "ERROR",
                    "status": f"ERROR ({exc})",
                    "reason": str(exc),
                }
            )
    return results
