import os


def get_script_dir():
    return os.path.dirname(__file__)


def get_file_path(filename):
    return os.path.join(get_script_dir(), filename)


# Overridable so the test suite doesn't append to the live database or log —
# importing utils.py configures logging at import time.
DATABASE_NAME = os.environ.get("PRAYPALBOT_DB") or get_file_path("praypalbot.db")
LOG_FILENAME = os.environ.get("PRAYPALBOT_LOG") or get_file_path("praypalbot.log")

# Stored in user_settings.lead_time when a user blocks the bot. Lives here so
# database_handler.py can use it without an import cycle. User-supplied lead
# times are validated to be >= 0, so they can never collide with it.
INACTIVE_LEAD_TIME = -1
