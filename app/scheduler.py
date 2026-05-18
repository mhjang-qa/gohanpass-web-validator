import asyncio
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import TIMEZONE
from app.runner import run_scenarios
from app.storage import load_schedule, save_schedule


DAY_MAP = {
    "mon": "mon",
    "tue": "tue",
    "wed": "wed",
    "thu": "thu",
    "fri": "fri",
    "sat": "sat",
    "sun": "sun",
}

scheduler = AsyncIOScheduler(timezone=ZoneInfo(TIMEZONE))


async def scheduled_run():
    schedule = load_schedule()
    scenarios = schedule.get("scenarios", [])
    if not schedule.get("enabled") or not scenarios:
        return
    await run_scenarios(scenarios, notion_upload=schedule.get("notion_upload", True), source="schedule")


def apply_schedule(schedule: dict):
    scheduler.remove_all_jobs()
    save_schedule(schedule)

    if not schedule.get("enabled"):
        return

    hour, minute = [int(part) for part in schedule.get("time", "09:00").split(":", 1)]
    days = ",".join(DAY_MAP[item] for item in schedule.get("days", []) if item in DAY_MAP)
    if not days:
        return

    scheduler.add_job(
        scheduled_run,
        "cron",
        day_of_week=days,
        hour=hour,
        minute=minute,
        id="go_hanpass_schedule",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
    apply_schedule(load_schedule())


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
