import datetime
from datetime import timedelta
from dateutil import parser

import pytz
import telegram
import uuid

from database_handler import deactivate_user, get_all_chat_ids, get_user_settings
from prayers import get_prayer_times

last_execution_time = None


def schedule_prayer_times(chat_id, location, lead_time, job_queue):
    """Schedules prayer reminders for the entire week, excluding inactive users.

    Args:
        chat_id (str): The user's chat ID.
        location (str): The user's location.
        lead_time (int): The lead time in minutes for reminders (optional).
        job_queue: The job queue to schedule reminders.
    """

    if lead_time == -1:  # Check if lead_time is the inactive flag
        # User has been deactivated, skipping user.
        print(f"User with ID {chat_id} has been deactivaed. Skipping user.")
        return

    response = get_prayer_times(location)

    if isinstance(response, str):
        print(f"Error getting prayer times for {location}: {response}")
        return

    # Extract prayer times and check for missing data
    try:
        timezone_offset = int(response.get("timezone_offset"))
    except (TypeError, ValueError):
        print(f"Invalid timezone offset in API response for {location}.")
        timezone_offset = 0

    if not timezone_offset:
        print(f"Timezone offset missing in API response for {location}.")
        timezone_offset = 0

    offset_timezone = datetime.timezone(datetime.timedelta(hours=timezone_offset))
    current_time = datetime.datetime.now(offset_timezone)
    delete_existing_reminders(job_queue, chat_id)

    for day_data in response["prayer_times"]:
        # Extract prayer times for the current day
        day_prayer_times = day_data
        prayer_date = day_prayer_times["date_for"]

        for prayer_name, prayer_time in day_prayer_times.items():
            if prayer_name == "date_for":
                continue

            # Construct datetime object for the prayer time
            datetime_str = f"{prayer_date} {prayer_time}"
            naive_datetime = parser.parse(datetime_str)
            adjusted_prayer_time = naive_datetime.replace(tzinfo=offset_timezone)

            # Check for past prayer times
            if adjusted_prayer_time < current_time:
                print(
                    f"Prayer time for {prayer_name} on {prayer_date} has already passed. Skipping schedule."
                )
                continue

            # Assuming job_queue uses UTC by default
            adjusted_prayer_time = adjusted_prayer_time.astimezone(pytz.utc)

            # Base job ID using chat_id, prayer_name, date, timezone offset, and lead time (if set)
            base_job_id = f"{chat_id}_{prayer_name}_{prayer_date}_{timezone_offset}_{uuid.uuid4()}"
            if lead_time:
                base_job_id += f"_{lead_time}"  # Append lead time if present

            # Schedule reminders
            # - Exact Prayer Time Reminder
            job_queue.run_once(
                send_prayer_reminder,
                adjusted_prayer_time,
                context={
                    "chat_id": chat_id,
                    "lead_time": None,
                    "prayer_name": prayer_name,
                },
                name=f"{base_job_id}_exact",
            )
            print(
                f"Scheduled exact prayer reminder for {prayer_name} on {prayer_date} at {adjusted_prayer_time} (Job ID: {base_job_id}_exact)"
            )

            # - Lead Time Reminder (Optional)
            if lead_time:
                lead_prayer_time = adjusted_prayer_time - timedelta(minutes=lead_time)
                job_queue.run_once(
                    send_prayer_reminder,
                    lead_prayer_time,
                    context={
                        "chat_id": chat_id,
                        "lead_time": lead_time,
                        "prayer_name": prayer_name,
                    },
                    name=f"{base_job_id}_lead",
                )
                print(
                    f"Scheduled lead time reminder for {prayer_name} on {prayer_date} at {lead_prayer_time} (Job ID: {base_job_id}_lead)"
                )


def delete_existing_reminders(job_queue, chat_id):
    """Deletes existing jobs that start with the given chat ID from the job queue.

    Args:
        job_queue: The apscheduler job queue to use (potentially unused).
        chat_id (int): The chat ID to match at the beginning of the job name.
    """
    for job in job_queue.scheduler.get_jobs():  # Using scheduler.get_jobs
        if job.name.startswith(f"{chat_id}_"):
            job.remove()
            print(f"Deleted existing job: {job.name}")


def send_prayer_reminder(context):
    """Sends a prayer reminder message to the user.

    Args:
        context (JobExecutionContext): The job execution context containing chat ID, prayer name, and optional lead time.
    """

    job = context.job
    chat_id = job.context["chat_id"]
    prayer_name = job.context.get("prayer_name")
    lead_time = job.context.get("lead_time")

    if lead_time:  # Check if lead_time exists
        message = f"Reminder: It's almost "
        if prayer_name.lower() == "shurooq":
            message += f"Shurooq time (in {lead_time} minutes)"  # Include lead time for Shurooq
        else:
            message += f"time for {prayer_name.title()} prayer. You have {lead_time} minutes to prepare."
    else:
        message = f"It's {('Shurooq time.' if prayer_name.lower() == 'shurooq' else f'time for {prayer_name.title()} prayer.')}"

    try:
        context.bot.send_message(chat_id, text=message)
    except telegram.error.Unauthorized as e:
        # User has blocked the bot, deactivate user from database
        print(f"User with ID {chat_id} has blocked the bot. Deactivating user.")
        deactivate_user(chat_id)


def reinitialize_reminders(updater):
    """Reinitializes all prayer reminders based on user settings in the database."""

    current_time = datetime.datetime.now().astimezone(pytz.utc)

    # Print current SGT time
    print(
        "Reinitializing reminders at",
        current_time.astimezone(pytz.timezone("Asia/Singapore")).strftime(
            "%H:%M:%S %Z"
        ),
    )

    global last_execution_time

    if last_execution_time is None or (current_time - last_execution_time) >= timedelta(
        days=3
    ):
        # First execution or at least 3 days since last execution
        last_execution_time = current_time  # Update last execution time
    else:
        print("Skipping reinitialization (less than 3 days since last execution).")
        return

    # Get all chat IDs
    chat_ids = get_all_chat_ids()

    for chat_id in chat_ids:
        print(f"Processing chat ID: {chat_id}")  # Print chat ID being processed

        user_settings = get_user_settings(chat_id)

        if not user_settings:
            print(
                f"Skipping chat ID {chat_id}: No user settings found"
            )  # Print reason for skipping
            continue

        location, lead_time = user_settings
        schedule_prayer_times(
            chat_id, location, lead_time, updater.dispatcher.job_queue
        )

    print("Reminder reinitialization complete!")  # Print completion message


def get_upcoming_reminder(chat_id, job_queue):
    """
    This function retrieves information about the upcoming scheduled prayer reminder
    for the given chat ID, considering both exact and lead time reminders.

    Args:
        chat_id (int): The chat ID of the user.
        job_queue (apscheduler.schedulers.base.BaseScheduler):
            The APScheduler job queue to use.

    Returns:
        dict or None:
            A dictionary containing details about the upcoming reminder
            (prayer_name, scheduled_time, lead_time_minutes, timezone_offset)
            if found, otherwise None.
    """
    upcoming_job = None

    matching_jobs = [
        job
        for job in job_queue.scheduler.get_jobs()
        if job.name.startswith(f"{chat_id}_") and job.name.endswith("_exact")
    ]

    if matching_jobs:
        # Find job with earliest next_run_time using a custom key function
        upcoming_job = min(matching_jobs, key=lambda job: job.next_run_time)
    else:
        upcoming_job = None

    # Now upcoming_job holds the job with the earliest next_run_time

    if upcoming_job:
        # Extract information from job name
        job_name_parts = upcoming_job.name.split("_")

        # Check for minimum expected parts (including potential lead time)
        if len(job_name_parts) < 6:
            return None  # Invalid format

        prayer_name = job_name_parts[1]  # Assuming prayer name is the second part
        timezone_offset = None  # Initialize timezone_offset

        # Extract timezone offset
        if len(job_name_parts) > 3:
            try:
                # Attempt to convert the part before potential lead time (assuming timezone offset)
                timezone_offset = int(job_name_parts[3])
            except ValueError:
                # If conversion fails, ignore and keep timezone_offset as None
                pass

        # Construct scheduled time with timezone offset (if available)
        offset_timezone = (
            pytz.utc
            if timezone_offset is None
            else datetime.timezone(datetime.timedelta(hours=timezone_offset))
        )

        scheduled_time = upcoming_job.next_run_time.astimezone(offset_timezone)
        scheduled_time_str = scheduled_time.strftime("%H:%M:%S %Z (%a)")

        # Calculate time difference
        now = datetime.datetime.now(offset_timezone)
        time_remaining = scheduled_time - now

        # Format time remaining (considering negative values for past prayers)
        if time_remaining < timedelta(seconds=0):  # Prayer time has already passed
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
        }

    else:
        return None


# Function to format time remaining in a more natural language way (optional)
def format_time_remaining_natural(days, hours, minutes):
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
