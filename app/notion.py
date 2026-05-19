from pathlib import Path
import re

from app.config import NOTION_UPLOAD, OUTPUT_DIR
from app.integrations.notion_uploader import NotionUploader
from PIL import Image


def _compact_status(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _image_path(value: str) -> str | None:
    path_text = str(value)
    if path_text.startswith("/output/"):
        path = OUTPUT_DIR / path_text.removeprefix("/output/")
    else:
        path = Path(path_text)

    if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return str(_resized_image_path(path))
    return None


def _resized_image_path(path: Path) -> Path:
    resized_dir = OUTPUT_DIR / "notion_resized"
    resized_dir.mkdir(parents=True, exist_ok=True)
    resized_path = resized_dir / f"{path.stem}_50{path.suffix.lower()}"

    if resized_path.exists() and resized_path.stat().st_mtime >= path.stat().st_mtime:
        return resized_path

    try:
        with Image.open(path) as image:
            width, height = image.size
            resized = image.resize((max(1, width // 2), max(1, height // 2)), Image.Resampling.LANCZOS)
            if resized.mode in ("RGBA", "P") and path.suffix.lower() in {".jpg", ".jpeg"}:
                resized = resized.convert("RGB")
            resized.save(resized_path)
            return resized_path
    except Exception:
        return path


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
