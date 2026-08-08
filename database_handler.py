import logging
import sqlite3

from config import DATABASE_NAME, INACTIVE_LEAD_TIME

logger = logging.getLogger(__name__)


def get_db_connection():
    """Opens a connection, creating the table on first use."""
    conn = sqlite3.connect(DATABASE_NAME)
    create_user_settings_table(conn)
    return conn, conn.cursor()


def close_db_connection(conn):
    """Commits and closes."""
    conn.commit()
    conn.close()


def create_user_settings_table(conn):
    """Creates the user_settings table if it doesn't exist."""
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS user_settings (
                chat_id INTEGER PRIMARY KEY,
                location TEXT,
                lead_time INTEGER
            )""")
    conn.commit()


def save_user_settings(chat_id, location, lead_time):
    """Inserts or updates one user's settings."""
    conn, c = get_db_connection()

    try:
        c.execute(
            """INSERT OR REPLACE INTO user_settings (chat_id, location, lead_time)
                     VALUES (?, ?, ?)""",
            (chat_id, location, lead_time),
        )
    except sqlite3.Error:
        logger.error("Error saving user settings for %s.", chat_id, exc_info=True)

    finally:
        close_db_connection(conn)


def get_user_settings(chat_id):
    """Returns (location, lead_time) for a chat ID, or None."""
    conn, c = get_db_connection()

    try:
        c.execute(
            "SELECT location, lead_time FROM user_settings WHERE chat_id = ?",
            (chat_id,),
        )
        user_settings = c.fetchone()
    except sqlite3.Error:
        logger.error("Error getting user settings for %s.", chat_id, exc_info=True)
        user_settings = None

    finally:
        close_db_connection(conn)

    return user_settings


def get_all_chat_ids():
    """Returns every known chat ID, or an empty list on error."""
    conn, c = get_db_connection()

    try:
        c.execute("SELECT chat_id FROM user_settings")
        chat_ids = [row[0] for row in c.fetchall()]
    except sqlite3.Error:
        logger.error("Error getting chat IDs.", exc_info=True)
        chat_ids = []  # Empty rather than None so callers can iterate safely.

    finally:
        close_db_connection(conn)

    return chat_ids


def deactivate_user(chat_id):
    """Marks a user inactive after they block the bot."""
    conn, c = get_db_connection()
    try:
        # Parameterized, like every other query here — never interpolate.
        c.execute(
            "UPDATE user_settings SET lead_time = ? WHERE chat_id = ?",
            (INACTIVE_LEAD_TIME, chat_id),
        )
    except sqlite3.Error:
        logger.error("Error deactivating user %s.", chat_id, exc_info=True)
    finally:
        close_db_connection(conn)
