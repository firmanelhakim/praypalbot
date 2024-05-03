#!/usr/bin/python3.9

from apscheduler.schedulers.background import BackgroundScheduler
from telegram.ext import (
    Updater,
    ConversationHandler,
    CommandHandler,
    Filters,
    MessageHandler,
)
import pytz
import telegram
import time

from utils import logging

from command_handler import (
    SET_LOCATION,
    SET_LEAD_TIME,
    start,
    location_handler,
    lead_time_handler,
    show_settings,
    today_prayer_times,
    upcoming_prayer_handler,
)
from credentials import TELEGRAM_BOT_TOKEN
from reminders import reinitialize_reminders
from send_email import send_email


def start_scheduler(scheduler, logger):
    """Starts the scheduler and logs the event."""
    try:
        scheduler.start()
        logger.info("Scheduler started successfully.")
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")


def get_active_jobs(scheduler):
    """Prints information about currently active jobs in the scheduler, showing next run time in Singapore Time (SGT)."""
    print("Active Jobs:")
    for job in scheduler.get_jobs():
        # Extract job name and next run time
        job_name = job.name
        next_run_time = job.next_run_time.astimezone(pytz.timezone("Asia/Singapore"))
        next_run_time_str = next_run_time.strftime("%Y-%m-%d %H:%M:%S (SGT)")
        # Format the message and print directly
        message = f"- Name: {job_name}, Next Run (SGT): {next_run_time_str}"
        print(message)


def handle_telegram_error(update, context):
    # Handle all Telegram errors
    error = context.error
    print(f"An error occurred: {error}")


def handle_read_timeout_error(update, context, updater):
    error = context.error
    if isinstance(error, telegram.error.TimedOut):
        print(f"Read timeout error occurred during update retrieval. Reconnecting...")
        # Implement reconnection logic
        updater.stop()
        time.sleep(5)  # Wait for some time before restarting
        updater.start_polling()


def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Register error handlers
    dp.add_error_handler(handle_telegram_error)
    dp.add_error_handler(handle_read_timeout_error, updater)

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: reinitialize_reminders(updater),
        "cron",
        name="PrayerTimeUpdate",
        hour="0",
        day_of_week="*",
        timezone="UTC",
    )

    scheduler.add_job(
        get_active_jobs,
        "cron",
        args=(scheduler,),  # Pass scheduler as argument
        hour="*",  # Run every hour
        day_of_week="*",
        timezone="UTC",
    )
    start_scheduler(scheduler, logging.getLogger(__name__))

    # Re-initialize reminders on startup
    reinitialize_reminders(updater)

    # Set up conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SET_LOCATION: [
                MessageHandler(Filters.text & ~Filters.command, location_handler)
            ],
            SET_LEAD_TIME: [
                MessageHandler(Filters.text & ~Filters.command, lead_time_handler)
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
        ],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("showsettings", show_settings))
    dp.add_handler(CommandHandler("nextsalat", upcoming_prayer_handler))
    dp.add_handler(CommandHandler("todayprayertimes", today_prayer_times))

    try:
        updater.start_polling()
        updater.idle()
    except telegram.error.NetworkError as e:
        print(f"Network error: {e}")
        # Send email notification for network error
        send_email(
            "PrayPalBot Network Error",
            f"Network error encountered: {e}",
        )
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        # Send email notification for general exception
        send_email(
            "PrayPalBot Error",
            f"An error occurred: {e}",
        )


if __name__ == "__main__":
    main()
