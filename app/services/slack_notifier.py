import logging
import os
from typing import Any

import requests


logger = logging.getLogger(__name__)


def resolve_result_url(result_summary: dict[str, Any]) -> str:
    for key in ("notion_url", "html_report_url", "dashboard_url", "result_url"):
        value = str(result_summary.get(key) or "").strip()
        if value:
            return value
    return "-"


def build_slack_payload(result_summary: dict[str, Any]) -> dict[str, str]:
    fail_count = int(result_summary.get("fail_count") or 0)
    result_url = resolve_result_url(result_summary)

    title = "⚠️ 테스트 완료 - 실패 발생" if fail_count > 0 else "✅ 테스트 완료"
    text = "\n".join(
        [
            title,
            f"실패: {fail_count}건",
            f"결과: {result_url}",
        ]
    )
    return {"text": text}


def send_slack_notification(result_summary: dict[str, Any]) -> bool:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL is not set. Slack notification skipped.")
        return False

    payload = build_slack_payload(result_summary)
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Slack notification failed: %s", exc)
        return False
