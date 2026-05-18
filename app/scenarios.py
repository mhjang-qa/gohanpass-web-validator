from pathlib import Path

from app.config import SCENARIO_DIR


def list_scenarios() -> list[dict]:
    excluded = {"sample_scenario.py", "01_login.py"}
    scenarios = []
    for path in sorted(SCENARIO_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        if path.name in excluded:
            continue
        scenarios.append(
            {
                "name": path.name,
                "stem": path.stem,
                "path": str(path),
            }
        )
    return scenarios


def resolve_scenario_paths(names: list[str]) -> list[Path]:
    available = {item["name"]: Path(item["path"]) for item in list_scenarios()}
    paths = []
    for name in names:
        if name in available:
            paths.append(available[name])
    return paths
