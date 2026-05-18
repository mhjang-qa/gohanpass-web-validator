import sys
import importlib.util
from pathlib import Path

from app.config import MOBILE_VALIDATOR_DIR, NOTION_UPLOAD


def upload_to_notion(run: dict):
    if not NOTION_UPLOAD:
        return None

    module_path = MOBILE_VALIDATOR_DIR / "app" / "integrations" / "notion_uploader.py"
    spec = importlib.util.spec_from_file_location("mobile_notion_uploader", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Notion uploader 로드 실패: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    NotionUploader = module.NotionUploader

    result_lines = []
    for scenario in run["scenarios"]:
        result_lines.append(f"[{scenario['name']}]")
        for item in scenario["results"]:
            result_lines.append(f"- {item['name']}: {item['status']}")
        result_lines.append("")

    uploader = NotionUploader()
    return uploader.upload_result(
        title=f"GO Hanpass 웹 자동리포트_{run['started_at'].replace(':', '').replace('-', '')[:15]}",
        version="1.0.0",
        platform="WEB_CHROME_SERVER",
        pass_count=run["summary"]["pass"],
        fail_count=run["summary"]["fail"],
        na_count=run["summary"]["na"],
        total_count=run["summary"]["total"],
        status="완료" if run["summary"]["fail"] == 0 else "실패",
        result_text="\n".join(result_lines),
        attachment_paths=[item for item in run.get("attachments", []) if Path(item).exists()],
    )
