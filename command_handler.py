import datetime
import logging

import pytz
from telegram.ext import ConversationHandler
from telegram.utils.helpers import escape_markdown

from database_handler import save_user_settings, get_user_settings
from prayers import get_prayer_times
from reminders import schedule_prayer_times, get_upcoming_reminder

logger = logging.getLogger(__name__)

# Conversation states for the /start setup flow.
SET_LOCATION, SET_LEAD_TIME = range(2)

# Lead time bounds, in minutes. The lower bound matters: -1 is the "user
# blocked the bot" sentinel, so a negative value would mute them forever.
MIN_LEAD_TIME = 0
MAX_LEAD_TIME = 24 * 60

# The location is user-supplied and must not be able to blow Telegram's limit.
MAX_LOCATION_LENGTH = 100


def start(update, context):
    # Legacy "Markdown" parse mode uses single asterisks for bold.
    welcome_message = (
        "Welcome to PrayPalBot, your Prayer Times Reminder Bot! Here's how you can use me:\n\n"
        "*/start* - Initialize PrayPalBot and set up your prayer times reminder.\n"
        "*/showsettings* - View your current settings for location and lead time.\n"
        "*/todayprayertimes* - Get today's prayer times for your location.\n"
        "*/nextsalat* - Shows the next upcoming prayer time reminder.\n\n"
        "You can start by sending me your location, for example, 'Singapore' or 'London, United Kingdom'."
    )
    update.message.reply_text(welcome_message, parse_mode="Markdown")
    return SET_LOCATION


def location_handler(update, context):
    """Stores the user's location and moves on to the lead-time question."""
    chat_id = update.message.chat_id
    location = update.message.text.strip()

    if not location or len(location) > MAX_LOCATION_LENGTH:
        update.message.reply_text(
            f"That doesn't look like a valid location. Please send a city name "
            f"of up to {MAX_LOCATION_LENGTH} characters, "
            f"for example 'Singapore' or 'London, United Kingdom'."
        )
        return SET_LOCATION

    # Collapse whitespace but keep the user's capitalization — .title() mangles
    # names like "OʻZbekiston" and non-Latin scripts.
    location = " ".join(location.split())
    save_user_settings(chat_id, location, None)

    # Reply first, so a scheduling failure can't leave the user with no response.
    update.message.reply_text(
        "Location set. If you want to receive a reminder before the exact prayer time, please send the lead time in minutes. Otherwise, send 'skip' to continue."
    )

    try:
        schedule_prayer_times(
            chat_id=chat_id,
            location=location,
            lead_time=None,
            job_queue=context.job_queue,
        )
    except Exception:
        logger.error("Error scheduling prayer times for %r.", location, exc_info=True)

    return SET_LEAD_TIME


def lead_time_handler(update, context):
    """Validates and stores the lead time, completing the setup flow."""
    text = update.message.text.strip().lower()
    if text == "skip":
        lead_time = None
        message = "Lead time skipped. Reminders will be sent at the exact prayer times."
    else:
        try:
            lead_time = int(text)
        except ValueError:
            update.message.reply_text(
                "Invalid lead time. Please send a valid number of minutes or send 'skip' to set no lead time."
            )
            return SET_LEAD_TIME

        # A negative value would schedule the reminder after the prayer, and -1
        # collides with the inactive sentinel — silently stopping all reminders.
        if not MIN_LEAD_TIME <= lead_time <= MAX_LEAD_TIME:
            update.message.reply_text(
                f"Please send a lead time between {MIN_LEAD_TIME} and "
                f"{MAX_LEAD_TIME} minutes, or send 'skip' to set no lead time."
            )
            return SET_LEAD_TIME

        if lead_time == 0:
            lead_time = None
            message = (
                "Lead time set to 0. Reminders will be sent at the exact prayer times."
            )
        else:
            message = f"Lead time set to {lead_time} minutes."

    chat_id = update.message.chat_id
    user_settings = get_user_settings(chat_id)

    if not user_settings:
        logger.warning("Settings not found for chat ID %s.", chat_id)
        update.message.reply_text(
            "I couldn't find your settings. Please run /start to set up again."
        )
        return ConversationHandler.END

    location, _ = user_settings
    save_user_settings(chat_id, location, lead_time)

    # Reply first, so a scheduling failure can't swallow the confirmation.
    update.message.reply_text(message)

    try:
        schedule_prayer_times(
            chat_id=chat_id,
            location=location,
            lead_time=lead_time,
            job_queue=context.job_queue,
        )
    except Exception:
        logger.error("Error scheduling prayer times for %r.", location, exc_info=True)

    return ConversationHandler.END


def show_settings(update, context):
    """Replies with the user's stored location and lead time."""
    chat_id = update.message.chat_id
    user_settings = get_user_settings(chat_id)
    if user_settings:
        location, lead_time = user_settings
        if location:
            message = "Your current settings:\n\n"
            message += f"* Location: {location}\n"
            if lead_time is not None:
                message += f"* Lead time: {lead_time} minutes\n"
            else:
                message += "* Lead time: Not set (reminders at exact prayer time)\n"
        else:
            message = "You haven't set your location yet. To receive prayer times and reminders, please set your location using the /start command."
    else:
        message = "You haven't set your location or prayer time preferences yet. Use the /start command to get started!"

    update.message.reply_text(message)
    return ConversationHandler.END


def today_prayer_times(update, context):
    """Replies with today's prayer times for the user's location."""
    chat_id = update.message.chat_id
    user_settings = get_user_settings(chat_id)
    if not user_settings:
        update.message.reply_text(
            "You haven't set your location or prayer time preferences yet. Use the /start command to get started!"
        )
        return

    location, _ = user_settings
    if not location:
        update.message.reply_text(
            "You haven't set your location yet. To receive prayer times, please set your location using the /start command."
        )
        return

    response = get_prayer_times(location)
    if isinstance(response, str):
        logger.error("Error getting prayer times for %r: %s", location, response)
        update.message.reply_text(response)
        return

    today = datetime.datetime.now(pytz.utc).date().strftime("%Y-%m-%d")
    filtered_prayer_times = None
    for entry in response["prayer_times"]:
        if entry.get("date_for") == today:
            filtered_prayer_times = {
                key: value for key, value in entry.items() if key != "date_for"
            }
            break

    if not filtered_prayer_times:
        update.message.reply_text(
            f"Could not retrieve prayer times for today ({today}). Please try again later."
        )
        return

    # The location routinely contains MarkdownV2 reserved characters
    # ("Cairo - Egypt"), which made Telegram reject the whole message.
    safe_location = escape_markdown(location, version=2)
    message = f"Today's prayer times for *{safe_location}*:\n\n"

    for prayer_name, prayer_time in filtered_prayer_times.items():
        safe_name = escape_markdown(prayer_name.title(), version=2)
        safe_time = escape_markdown(str(prayer_time), version=2)
        message += f"*{safe_name}*: {safe_time}\n"

    context.bot.send_message(chat_id, text=message, parse_mode="MarkdownV2")


def upcoming_prayer_handler(update, context):
    """Replies with the user's next scheduled reminder."""
    chat_id = update.message.chat_id
    upcoming_reminder = get_upcoming_reminder(chat_id, context.job_queue)

    if not upcoming_reminder:
        context.bot.send_message(
            chat_id,
            text="You don't have any upcoming prayer reminders. Use the /start command to get started!",
        )
        return

    prayer_name = upcoming_reminder["prayer_name"]
    # Shurooq is sunrise, not a prayer — drop the word for it.
    label = "" if prayer_name.lower() == "shurooq" else "Prayer "

    message_text = f"Your upcoming {label.lower()}reminder:\n\n"
    message_text += f"* {label}Name: {prayer_name.title()}\n"
    message_text += f"* Scheduled Time: {upcoming_reminder['scheduled_time']}\n"
    message_text += f"* Time Remaining: {upcoming_reminder.get('time_remaining')}\n"

    context.bot.send_message(chat_id, text=message_text)
