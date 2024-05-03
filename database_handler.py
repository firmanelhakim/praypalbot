from config import DATABASE_NAME
import sqlite3


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_NAME)

    # Create table if it doesn't exist
    create_user_settings_table(conn)

    return conn, conn.cursor()


def close_db_connection(conn):
    """Commits changes and closes the connection to the database."""
    conn.commit()
    conn.close()


def create_user_settings_table(conn):
    """Creates the user_settings table in the database if it doesn't exist."""
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_settings (
                chat_id INTEGER PRIMARY KEY,
                location TEXT,
                lead_time INTEGER
            )"""
    )
    conn.commit()


def save_user_settings(chat_id, location, lead_time):
    """Saves user settings to the database."""
    conn, c = get_db_connection()

    try:
        # Insert or update user settings based on chat ID
        c.execute(
            """INSERT OR REPLACE INTO user_settings (chat_id, location, lead_time)
                     VALUES (?, ?, ?)""",
            (chat_id, location, lead_time),
        )
    except sqlite3.Error as e:
        print(f"Error saving user settings: {e}")

    finally:
        close_db_connection(conn)


def get_user_settings(chat_id):
    """Retrieves user settings from the database based on chat ID."""
    conn, c = get_db_connection()

    try:
        # Retrieve user settings based on chat ID
        c.execute(
            "SELECT location, lead_time FROM user_settings WHERE chat_id = ?",
            (chat_id,),
        )
        user_settings = c.fetchone()
    except sqlite3.Error as e:
        print(f"Error getting user settings: {e}")
        user_settings = None  # Indicate error by returning None

    finally:
        close_db_connection(conn)

    return user_settings


def get_all_chat_ids():
    """Retrieves a list of chat IDs from the database."""
    conn, c = get_db_connection()

    try:
        c.execute("SELECT chat_id FROM user_settings")
        chat_ids = [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        print(f"Error getting chat_id: {e}")
        chat_ids = None  # Indicate error by returning None

    finally:
        close_db_connection(conn)

    return chat_ids


def deactivate_user(chat_id):
    """
    Marks a user as inactive in the database based on chat ID.
    """
    conn, c = get_db_connection()
    try:
        # Update user status to a flag value indicating inactive
        c.execute(
            f"UPDATE user_settings SET lead_time = -1 WHERE chat_id = {chat_id}"
        )  # Set lead_time to -1
    except sqlite3.Error as err:
        print(f"Error deactivating user: {err}")
    finally:
        close_db_connection(conn)
