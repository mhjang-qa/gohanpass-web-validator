from pathlib import Path
import re

from app.config import NOTION_UPLOAD, OUTPUT_DIR
from app.integrations.notion_uploader import NotionUploader


def _compact_status(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _image_path(value: str) -> str | None:
    path_text = str(value)
    if path_text.startswith("/output/"):
        path = OUTPUT_DIR / path_text.removeprefix("/output/")
    else:
        path = Path(path_text)

    if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return str(path)
    return None


def upload_to_notion(run: dict):
    if not NOTION_UPLOAD:
        return None

    result_lines = []
    for scenario in run["scenarios"]:
        result_lines.append(f"[{scenario['name']}]")
        for item in scenario["results"]:
            result_lines.append(f"- {item['name']}: {_compact_status(item['status'])}")
        result_lines.append("")

    uploader = NotionUploader()
    attachments = [
        path
        for item in run.get("attachments", [])
        if (path := _image_path(item))
    ]
    scenario_snapshots = {}
    for scenario in run.get("scenarios", []):
        snapshots = [
            path
            for snapshot in scenario.get("snapshots", [])
            if (path := _image_path(snapshot))
        ]
        if snapshots:
            scenario_snapshots[scenario["name"]] = snapshots

    return uploader.upload_result(
        title=f"GO Hanpass 웹 자동리포트_{run['started_at'].replace(':', '').replace('-', '')[:15]}",
        version="1.0.0",
        platform="WEB_CHROME_SERVER",
        pass_count=run["summary"]["pass"],
        fail_count=run["summary"]["fail"],
        na_count=run["summary"]["na"],
        total_count=run["summary"]["total"],
        status="성공" if run["summary"]["fail"] == 0 else "실패",
        result_text="\n".join(result_lines),
        scenario_snapshots=scenario_snapshots,
        attachment_paths=attachments,
    )
