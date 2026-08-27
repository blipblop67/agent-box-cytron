"""
Background scheduler for flows that should run on their own, not just when
someone clicks Run. One APScheduler instance per process, loaded at startup
with every enabled schedule already in the database, so restarting the hub
doesn't lose anyone's schedules.

Two trigger types on purpose, not raw cron - "every 30 minutes" and "daily at
9:00" cover the overwhelming majority of what someone building their first
agent actually wants, without asking a newcomer to learn cron syntax.

Also runs a fixed-interval background job checking Telegram triggers for
new messages (see telegram_poller.py) - this is what makes "message the
bot and get a reply, from anywhere" actually work, instead of a flow only
ever running when someone's looking at the hub and clicks Run.
"""
import json
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import db, flow_engine, telegram_poller

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()

TELEGRAM_POLL_SECONDS = 3  # felt-instant for a chat, gentle enough not to trip Telegram's rate limits


def start() -> None:
    for schedule in db.list_all_enabled_schedules():
        _add_job(schedule)
    _scheduler.add_job(
        _poll_telegram_triggers,
        trigger=IntervalTrigger(seconds=TELEGRAM_POLL_SECONDS),
        id="telegram-trigger-poll",
        replace_existing=True,
        max_instances=1,  # a slow poll (network hiccup) shouldn't stack up overlapping runs
    )
    _scheduler.start()


def _poll_telegram_triggers() -> None:
    try:
        telegram_poller.check_all_triggers()
    except Exception:  # noqa: BLE001 - must never take the whole scheduler down
        logger.exception("Telegram trigger polling failed")


def shutdown() -> None:
    _scheduler.shutdown(wait=False)


def _trigger_for(schedule):
    if schedule["trigger_type"] == "interval":
        return IntervalTrigger(minutes=schedule["interval_minutes"])
    hour, minute = (int(part) for part in schedule["daily_time"].split(":"))
    return CronTrigger(hour=hour, minute=minute)


def _add_job(schedule) -> None:
    _scheduler.add_job(
        _run_schedule,
        trigger=_trigger_for(schedule),
        id=schedule["id"],
        args=[schedule["id"]],
        replace_existing=True,
        misfire_grace_time=300,
    )


def sync_job(schedule_id: str) -> None:
    """Call after creating/updating/deleting a schedule so the already-running
    scheduler picks up the change immediately, without a hub restart."""
    schedule = db.get_schedule(schedule_id)
    if schedule is None or not schedule["enabled"]:
        remove_job(schedule_id)
        return
    _add_job(schedule)


def remove_job(schedule_id: str) -> None:
    if _scheduler.get_job(schedule_id):
        _scheduler.remove_job(schedule_id)


def _run_schedule(schedule_id: str) -> None:
    schedule = db.get_schedule(schedule_id)
    if schedule is None:
        return

    flow = db.get_flow(schedule["flow_id"])
    if flow is None:
        db.record_schedule_run(schedule_id, "error")
        db.create_schedule_run(schedule_id, schedule["flow_id"], "error", None, "Flow no longer exists", None)
        return

    graph = json.loads(flow["graph_json"])
    try:
        # Google nodes authenticate via the hub-wide service account, not
        # whoever created this schedule - each node's own "Impersonate"
        # field (if set) decides which Workspace person it acts as
        result = flow_engine.run_flow(graph, schedule["input_text"], schedule["created_by"], flow_id=flow["id"])
        db.record_schedule_run(schedule_id, "success")
        db.create_schedule_run(schedule_id, flow["id"], "success", result["output"], None, json.dumps(result["trace"]))
    except flow_engine.FlowError as exc:
        db.record_schedule_run(schedule_id, "error")
        db.create_schedule_run(schedule_id, flow["id"], "error", None, str(exc), None)
    except Exception as exc:  # noqa: BLE001 - a scheduled run failing must never take the scheduler down
        logger.exception("Scheduled run failed for schedule %s", schedule_id)
        db.record_schedule_run(schedule_id, "error")
        db.create_schedule_run(schedule_id, flow["id"], "error", None, str(exc), None)
