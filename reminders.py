import datetime
import logging
import uuid
from datetime import timedelta

import pytz
import telegram
from dateutil import parser

from config import INACTIVE_LEAD_TIME
from database_handler import deactivate_user, get_all_chat_ids, get_user_settings
from prayers import get_prayer_times

logger = logging.getLogger(__name__)

# Guards against startup and the midnight cron both firing within seconds.
REINIT_MIN_INTERVAL_MINUTES = 60

last_execution_time = None


def _localize(naive_datetime, tzinfo):
    """Attaches a timezone to a naive local datetime, DST-correctly.

    pytz needs localize() rather than replace(tzinfo=...) — the latter attaches
    the zone's LMT offset (Asia/Kolkata becomes +5:53). Times that are ambiguous
    or non-existent across a DST boundary resolve to the post-transition offset.
    """
    try:
        return tzinfo.localize(naive_datetime, is_dst=None)
    except AttributeError:
        # Fixed-offset tzinfo (not a pytz zone) has no localize().
        return naive_datetime.replace(tzinfo=tzinfo)
    except (pytz.AmbiguousTimeError, pytz.NonExistentTimeError):
        return tzinfo.localize(naive_datetime, is_dst=False)


def schedule_prayer_times(chat_id, location, lead_time, job_queue):
    """Schedules a week of prayer reminders, skipping inactive users.

    Args:
        chat_id (int): The user's chat ID.
        location (str): The user's location.
        lead_time (int or None): Minutes before each prayer to also remind.
        job_queue: The PTB JobQueue to schedule on.
    """
    if lead_time == INACTIVE_LEAD_TIME:
        logger.info("User with ID %s has been deactivated. Skipping user.", chat_id)
        return

    response = get_prayer_times(location)

    if isinstance(response, str):
        logger.error("Error getting prayer times for %r: %s", location, response)
        return

    # The IANA name keeps the math DST-aware and correct for half-hour zones
    # (Asia/Kolkata +5:30). An integer offset truncated these and drifted.
    timezone_name = response.get("timezone") or "UTC"
    try:
        local_timezone = pytz.timezone(timezone_name)
    except Exception:
        logger.error(
            "Unusable timezone %r for %r; falling back to UTC.", timezone_name, location
        )
        local_timezone = pytz.utc

    current_time = datetime.datetime.now(pytz.utc)
    delete_existing_reminders(job_queue, chat_id)

    for day_prayer_times in response["prayer_times"]:
        prayer_date = day_prayer_times["date_for"]

        for prayer_name, prayer_time in day_prayer_times.items():
            if prayer_name == "date_for":
                continue

            datetime_str = f"{prayer_date} {prayer_time}"
            try:
                naive_datetime = parser.parse(datetime_str)
            except (ValueError, OverflowError):
                logger.warning(
                    "Could not parse prayer time %r for %r; skipping.",
                    datetime_str,
                    location,
                )
                continue

            adjusted_prayer_time = _localize(naive_datetime, local_timezone).astimezone(
                pytz.utc
            )

            if adjusted_prayer_time < current_time:
                continue

            base_job_id = f"{chat_id}_{prayer_name}_{prayer_date}_{uuid.uuid4()}"

            job_queue.run_once(
                send_prayer_reminder,
                adjusted_prayer_time,
                context={
                    "chat_id": chat_id,
                    "lead_time": None,
                    "prayer_name": prayer_name,
                    "timezone": timezone_name,
                    "scheduled_utc": adjusted_prayer_time.isoformat(),
                },
                name=f"{base_job_id}_exact",
            )

            if lead_time:
                lead_prayer_time = adjusted_prayer_time - timedelta(minutes=lead_time)
                # Skip past lead jobs, or they fire the moment they're scheduled.
                if lead_prayer_time < current_time:
                    continue
                job_queue.run_once(
                    send_prayer_reminder,
                    lead_prayer_time,
                    context={
                        "chat_id": chat_id,
                        "lead_time": lead_time,
                        "prayer_name": prayer_name,
                        "timezone": timezone_name,
                        "scheduled_utc": lead_prayer_time.isoformat(),
                    },
                    name=f"{base_job_id}_lead",
                )

    logger.info(
        "Scheduled reminders for chat %s (%s, %s, lead_time=%s).",
        chat_id,
        location,
        timezone_name,
        lead_time,
    )


def delete_existing_reminders(job_queue, chat_id):
    """Removes every scheduled job belonging to the given chat ID."""
    removed = 0
    for job in job_queue.scheduler.get_jobs():
        if job.name.startswith(f"{chat_id}_"):
            job.remove()
            removed += 1
    if removed:
        logger.info("Deleted %d existing job(s) for chat %s.", removed, chat_id)


def send_prayer_reminder(context):
    """Sends one reminder. The job context carries chat_id, prayer_name, lead_time."""
    job = context.job
    chat_id = job.context["chat_id"]
    prayer_name = job.context.get("prayer_name") or "prayer"
    lead_time = job.context.get("lead_time")

    is_shurooq = prayer_name.lower() == "shurooq"

    if lead_time:
        if is_shurooq:
            message = f"Reminder: It's almost Shurooq time (in {lead_time} minutes)."
        else:
            message = (
                f"Reminder: It's almost time for {prayer_name.title()} prayer. "
                f"You have {lead_time} minutes to prepare."
            )
    else:
        message = (
            "It's Shurooq time."
            if is_shurooq
            else f"It's time for {prayer_name.title()} prayer."
        )

    try:
        context.bot.send_message(chat_id, text=message)
    except telegram.error.Unauthorized:
        # Blocked by the user — stop scheduling for them.
        logger.info("User with ID %s has blocked the bot. Deactivating user.", chat_id)
        deactivate_user(chat_id)
    except telegram.error.TelegramError:
        logger.error("Failed to send reminder to chat %s.", chat_id, exc_info=True)


def reinitialize_reminders(updater):
    """Reschedules every user's reminders from the database.

    Runs on startup and from the midnight-UTC cron. Daily refresh matters
    because prayer times and DST offsets both change, and the prayers.py cache
    only holds for 24h.
    """
    global last_execution_time

    current_time = datetime.datetime.now(pytz.utc)

    if last_execution_time is not None and (
        current_time - last_execution_time
    ) < timedelta(minutes=REINIT_MIN_INTERVAL_MINUTES):
        logger.info("Skipping reinitialization (ran less than an hour ago).")
        return

    last_execution_time = current_time
    logger.info("Reinitializing reminders at %s.", current_time.isoformat())

    chat_ids = get_all_chat_ids()
    if not chat_ids:
        logger.info("No users to reinitialize.")
        return

    scheduled = 0
    for chat_id in chat_ids:
        user_settings = get_user_settings(chat_id)

        if not user_settings:
            logger.warning("Skipping chat ID %s: no user settings found.", chat_id)
            continue

        location, lead_time = user_settings
        if not location:
            logger.info("Skipping chat ID %s: no location set.", chat_id)
            continue

        try:
            schedule_prayer_times(
                chat_id, location, lead_time, updater.dispatcher.job_queue
            )
            scheduled += 1
        except Exception:
            # One bad user must not abort the refresh for everyone else.
            logger.error(
                "Failed to reinitialize reminders for chat %s.", chat_id, exc_info=True
            )

    logger.info("Reminder reinitialization complete (%d user(s)).", scheduled)


def _job_context(aps_job):
    """Returns the PTB job context dict behind an APScheduler job, or None.

    PTB stores a CallbackContext in the APScheduler job's `args`, with the
    reminder payload on `job.context`. Reading it beats parsing the job *name*,
    which broke whenever the name format changed.
    """
    for arg in getattr(aps_job, "args", ()) or ():
        job = getattr(arg, "job", None) or (arg if hasattr(arg, "context") else None)
        context = getattr(job, "context", None)
        if isinstance(context, dict):
            return context
    return None


def get_upcoming_reminder(chat_id, job_queue):
    """Returns the user's next pending reminder, or None.

    Considers both exact and lead-time jobs.

    Returns:
        dict with prayer_name, scheduled_time, time_remaining and lead_time.
    """
    matching_jobs = [
        job
        for job in job_queue.scheduler.get_jobs()
        if job.name.startswith(f"{chat_id}_") and job.next_run_time is not None
    ]

    if not matching_jobs:
        return None

    upcoming_job = min(matching_jobs, key=lambda job: job.next_run_time)

    # Prefer the structured context; the job name is only a fallback for the
    # prayer name, which has always been its second underscore-field.
    context = _job_context(upcoming_job) or {}
    prayer_name = context.get("prayer_name")
    lead_time = context.get("lead_time")
    timezone_name = context.get("timezone")

    if not prayer_name:
        name_parts = upcoming_job.name.split("_")
        if len(name_parts) < 2:
            return None
        prayer_name = name_parts[1]

    # Show the time in the user's own timezone when known.
    try:
        display_timezone = pytz.timezone(timezone_name) if timezone_name else pytz.utc
    except Exception:
        display_timezone = pytz.utc

    scheduled_time = upcoming_job.next_run_time.astimezone(display_timezone)
    scheduled_time_str = scheduled_time.strftime("%H:%M:%S %Z (%a)")

    time_remaining = scheduled_time - datetime.datetime.now(pytz.utc)

    if time_remaining < timedelta(seconds=0):
        time_remaining_str = "Prayer time has already passed."
    else:
        days = time_remaining.days
        hours = time_remaining.seconds // 3600 % 24
        minutes = time_remaining.seconds // 60 % 60
        time_remaining_str = format_time_remaining_natural(days, hours, minutes)

    return {
        "prayer_name": prayer_name,
        "scheduled_time": scheduled_time_str,
        "time_remaining": time_remaining_str,
        "lead_time": lead_time,
    }


def format_time_remaining_natural(days, hours, minutes):
    """Renders a countdown as "in 2 hours and 5 minutes"."""
    time_components = []
    if days > 0:
        time_components.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        time_components.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        time_components.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if not time_components:
        return "Prayer time is about to start."
    return f"in {' and '.join(time_components)}."
