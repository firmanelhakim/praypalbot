from telegram.ext import ConversationHandler
import datetime
import pytz

from database_handler import save_user_settings, get_user_settings
from prayers import get_prayer_times
from reminders import schedule_prayer_times, get_upcoming_reminder

# Define states for user setup process
SET_LOCATION, SET_LEAD_TIME = range(2)


def start(update, context):
    welcome_message = (
        "Welcome to PrayPalBot, your Prayer Times Reminder Bot! Here's how you can use me:\n\n"
        "**/start** - Initialize PrayPalBot and set up your prayer times reminder.\n"
        "**/showsettings** - View your current settings for location, timezone offset, and lead time.\n"
        "**/todayprayertimes** - Get today's prayer times for your location.\n"
        "**/nextsalat** - Shows the next upcoming prayer time reminder.\n\n"
        "You can start by sending me your location, for example, 'Singapore'."
    )
    update.message.reply_text(welcome_message, parse_mode="Markdown")
    return SET_LOCATION


def location_handler(update, context):
    """Handles user input for location.

    Args:
        update (Update): Update object from Telegram Bot API.
        context (Context): Context object from Telegram Bot API.
    """
    chat_id = update.message.chat_id
    location = update.message.text.strip().title()
    save_user_settings(chat_id, location, None)

    schedule_prayer_times(
        chat_id=chat_id,
        location=location,
        lead_time=None,
        job_queue=context.job_queue,
    )

    update.message.reply_text(
        "Location set. If you want to receive a reminder before the exact prayer time, please send the lead time in minutes. Otherwise, send 'skip' to continue."
    )
    return SET_LEAD_TIME


def lead_time_handler(update, context):
    text = update.message.text.lower()
    if text == "skip":
        lead_time = None
        message = "Lead time skipped. Reminders will be sent at the exact prayer times."
    else:
        try:
            lead_time = int(text)
            message = f"Lead time set to {lead_time} minutes."

        except ValueError:
            update.message.reply_text(
                "Invalid lead time. Please send a valid number of minutes or send 'skip' to set no lead time."
            )
            return SET_LEAD_TIME

    chat_id = update.message.chat_id
    user_settings = get_user_settings(chat_id)

    if not user_settings:
        print(f"Settings not found for chat ID {chat_id}.")
        return

    location, _ = user_settings
    save_user_settings(chat_id, location, lead_time)

    schedule_prayer_times(
        chat_id=chat_id,
        location=location,
        lead_time=lead_time,
        job_queue=context.job_queue,
    )

    update.message.reply_text(message)

    return ConversationHandler.END


def show_settings(update, context):
    """Displays the user's current settings for prayer times and reminders.

    Args:
        update (Update): Update object from Telegram Bot API.
        context (Context): Context object from Telegram Bot API.

    Returns:
        int: ConversationHandler.END to indicate the end of the conversation.
    """
    chat_id = update.message.chat_id
    user_settings = get_user_settings(chat_id)
    if user_settings:
        location, lead_time = user_settings
        # Check if location is set within user_settings
        if location:
            message = f"Your current settings:\n\n"
            message += f"* Location: {location}\n"
            if lead_time is not None:
                message += f"* Lead time: {lead_time} minutes\n"
            else:
                message += "* Lead time: Not set (reminders at exact prayer time)\n"
        else:
            # Location not set - inform user
            message = "You haven't set your location yet. To receive prayer times and reminders, please set your location using the /start command."
    else:
        # Handle case where no user settings are found
        message = "You haven't set your location or prayer time preferences yet. Use the /start command to get started!"

    update.message.reply_text(message)
    return ConversationHandler.END  # End conversation after showing settings


def today_prayer_times(update, context):
    """Displays today's prayer times for the user's location.

    Args:
      update (Update): Update object from Telegram Bot API.
      context (Context): Context object from Telegram Bot API.

    Returns:
      None
    """
    chat_id = update.message.chat_id
    user_settings = get_user_settings(chat_id)
    if user_settings:
        location, _ = user_settings
        # Check if location is set within user_settings
        if location:
            response = get_prayer_times(location)

            if isinstance(response, str):
                print(f"Error getting prayer times for {location}: {response}")
                update.message.reply_text(response)  # Display error message
                return

            # Extract prayer times from the response dictionary
            prayer_times = response["prayer_times"]

            # Today's date
            today = datetime.datetime.now(pytz.utc).date()
            filtered_prayer_times = None

            for entry in prayer_times:
                try:
                    date_for = datetime.datetime.strptime(
                        entry["date_for"], "%Y-%m-%d"
                    ).strftime("%Y-%m-%d")
                    if date_for == today.strftime("%Y-%m-%d"):
                        filtered_prayer_times = {
                            key: value
                            for key, value in entry.items()
                            if key != "date_for"
                        }
                except ValueError:
                    pass

            if filtered_prayer_times:
                message = f"Today's prayer times for *{location}*:\n\n"

                for prayer_name, time in filtered_prayer_times.items():
                    message += f"*{prayer_name.title()}*: {time}\n"

                context.bot.send_message(chat_id, text=message, parse_mode="MarkdownV2")
            else:
                # No prayer times found for today (potentially an API issue)
                message = f"Could not retrieve prayer times for today ({today.strftime('%Y-%m-%d')}). Please try again later."
                update.message.reply_text(message)

        else:
            # Location not set - inform user
            message = "You haven't set your location yet. To receive prayer times, please set your location using the /start command."
            update.message.reply_text(message)
    else:
        # Handle case where no user settings are found
        message = "You haven't set your location or prayer time preferences yet. Use the /start command to get started!"
        update.message.reply_text(message)


def upcoming_prayer_handler(update, context):
    """
    This handler retrieves information about the upcoming prayer reminder
    for the user and sends a message with the details.

    Args:
        update (Update): Update object from Telegram Bot API.
        context (Context): Context object from Telegram Bot API.
    """
    chat_id = update.message.chat_id
    upcoming_reminder = get_upcoming_reminder(chat_id, context.job_queue)

    if upcoming_reminder:
        prayer_name = upcoming_reminder["prayer_name"]
        scheduled_time = upcoming_reminder["scheduled_time"]
        time_remaining = upcoming_reminder.get("time_remaining")

        message_text = f"Your upcoming {'prayer ' if prayer_name.lower() != 'shurooq' else ''}reminder:\n\n"
        message_text += f"* {'Prayer ' if prayer_name.lower() != 'shurooq' else ''}Name: {prayer_name.title()}\n"
        message_text += f"* Scheduled Time: {scheduled_time}\n"
        message_text += f"* Time Remaining: {time_remaining}\n"

        context.bot.send_message(chat_id, text=message_text)
    else:
        # Handle case where no upcoming reminder is found
        message_text = "You don't have any upcoming prayer reminders. Use the /start command to get started!"
        context.bot.send_message(chat_id, text=message_text)
