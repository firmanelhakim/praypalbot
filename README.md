## Prayer Reminder Bot (@PrayPalBot)

This repository contains the code for a prayer reminder bot named [**@PrayPalBot**](https://t.me/PrayPalBot) that interacts with users via Telegram and utilizes the [Muslim Salah API](https://muslimsalat.com/) for prayer time data. User settings are stored in an SQLite database.

**Features:**

* Schedules prayer reminders based on user location and lead time preferences (handled in `reminders.py`).
* Fetches prayer times and handles timezones (in `prayers.py`).
* Manages user interactions through Telegram commands (implemented in `command_handler.py`).
    * Guides users through setup process (`/start`)
    * Allows users to view current settings (`/showsettings`)
    * Provides today's prayer times for the user's location (`/todayprayertimes`)
    * Shows the next upcoming prayer time reminder (`/nextsalat`)
* Offers optional email notifications for errors (requires configuration in `send_email.py` and `credentials.py`).
* Utilizes background tasks (`apscheduler`) to automatically update reminders daily at midnight (UTC).
* Logs errors and scheduler activity.

**Project Structure:**

1. `main.py`: The main script responsible for coordinating all functionalities.
2. `command_handler.py`: Handles user interactions through Telegram commands.
3. `database_handler.py`: Manages user settings in an SQLite database.
4. `prayers.py`: Fetches prayer times and timezone information from an external API.
5. `reminders.py`: Handles scheduling and sending prayer reminders to users.
6. `send_email.py`: Provides a function to send emails using Gmail's SMTP server.
7. `utils.py`: Contains utility functions and configurations for the bot, including logging and caching.
8. `config.py`: Defines configuration settings like database name and log file path.
9. `credentials.py`: Stores sensitive information like API keys and email credentials.
10. `run.sh`: A shell script to manage the bot process (ensures only one instance runs).

**Dependencies:**

* `python-telegram-bot==13.7.0` (for Telegram bot interaction)
* `apscheduler` (for job scheduling)
* `cachetools` (for caching functionality)
* `requests` (for making API requests)
* `sqlite3` (for database access)
* `pytz` (for timezone handling)

**Getting Started:**

1. Clone the repository: `git clone https://github.com/firmanelhakim/praypalbot.git`
2. Install required dependencies: `pip install -r requirements.txt`
3. **Create an empty file named `praypalbot.db` in the project directory.** The bot uses this SQLite database to store user settings.
4. Configure settings (API keys, database name, email settings - modify `credentials.py` and `config.py` accordingly)
5. Run the bot: `./run.sh` (assuming `run.sh` has execute permissions) **OR** simply run with `python3 main.py`

**Security Considerations:**

* **DO NOT commit `credentials.py` to version control.** Use environment variables or a secure configuration file for sensitive information.
* Consider using app passwords for programmatic access to email instead of storing actual passwords.

**How to Contribute**

We welcome contributions to this project! Here are some ways you can help:

* **Report issues:** If you encounter any bugs or have suggestions for improvement, please create an issue on this repository.
* **Fix bugs:** If you're comfortable with the codebase, feel free to submit a pull request with your fix. 
* **Propose new features:** If you have ideas for new functionality, open an issue to discuss it and potentially submit a pull request.

**Making a Pull Request**

1. Fork this repository.
2. Clone your forked repository to your local machine.
3. Make your changes and commit them.
4. Push your changes to your forked repository.
5. Open a pull request from your forked repository to the upstream repository.

**We appreciate any contributions you can make!**

**License:**

This project is licensed under the MIT License: [https://opensource.org/licenses/MIT](https://opensource.org/licenses/MIT). This license allows for free use, modification, and distribution of the code, with attribution to the original author.

**Additional Notes:**

* Feel free to contact the project maintainers if you have any questions or need assistance.

