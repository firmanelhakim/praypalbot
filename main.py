#!/usr/bin/env python3

import logging

import telegram
from apscheduler.schedulers.background import BackgroundScheduler
from telegram.ext import (
    Updater,
    ConversationHandler,
    CommandHandler,
    Filters,
    MessageHandler,
)

import utils  # noqa: F401  — imported for its logging/cache setup side effects
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

logger = logging.getLogger(__name__)


def start_scheduler(scheduler):
    """Starts the scheduler and logs the event."""
    try:
        scheduler.start()
        logger.info("Scheduler started successfully.")
    except Exception:
        logger.error("Error starting scheduler.", exc_info=True)


def get_active_jobs(scheduler):
    """Logs information about currently active jobs in the scheduler."""
    jobs = scheduler.get_jobs()
    logger.info("Active jobs: %d", len(jobs))


def handle_telegram_error(update, context):
    """Handles every error raised while processing an update.

    Must take exactly (update, context). PTB's second positional argument to
    add_error_handler is `run_async`, not user data — passing anything truthy
    there makes PTB call this with two arguments and raise TypeError.
    """
    error = context.error

    # Network blips are self-healing; Updater retries polling on its own.
    if isinstance(error, (telegram.error.TimedOut, telegram.error.NetworkError)):
        logger.warning("Transient Telegram network error: %s", error)
        return

    logger.error("Unhandled error while processing update.", exc_info=error)


def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # No extra arguments here — see handle_telegram_error's docstring.
    dp.add_error_handler(handle_telegram_error)

    scheduler = BackgroundScheduler(timezone="UTC")

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
        args=(scheduler,),
        hour="*",
        day_of_week="*",
        timezone="UTC",
    )
    start_scheduler(scheduler)

    reinitialize_reminders(updater)

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
        logger.info("Starting polling.")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.critical("Bot stopped by an unhandled exception.", exc_info=True)
        send_email("PrayPalBot Error", f"An error occurred: {e}")
        raise
    finally:
        # Stop the scheduler so a restart can't leave an orphaned thread.
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
