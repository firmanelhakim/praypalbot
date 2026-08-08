## Prayer Reminder Bot (@PrayPalBot)

This repository contains the code for a prayer reminder bot named [**@PrayPalBot**](https://t.me/PrayPalBot) that interacts with users via Telegram and utilizes the [AlAdhan Prayer Times API](https://aladhan.com/prayer-times-api) for prayer time data. User settings are stored in an SQLite database.

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
9. `credentials.py`: Loads secrets from the environment (or a local `.env`). Contains no secrets itself.
10. `run.sh`: A shell script to manage the bot process (ensures only one instance runs).
11. `test_prayers.py`, `test_handlers.py`: Unit tests (no network access required).

**Dependencies:**

Pinned in `requirements.txt`. Highlights:

* `python-telegram-bot==13.15` (Telegram bot interaction — v13 sync API, not v20+)
* `APScheduler` (for job scheduling)
* `cachetools` (for caching functionality)
* `requests` (for making API requests)
* `sqlite3` (stdlib, for database access)
* `pytz` (for timezone handling)

> Do **not** `pip install telegram` — that is an unrelated package that shadows
> `python-telegram-bot` under the same import name.

> **`pip check` reports a conflict, and that is expected.** PTB 13's metadata
> declares `APScheduler==3.6.3` and `cachetools==4.2.2`. Those pins are
> over-tight: PTB only touches `BackgroundScheduler` and `cachetools.LRUCache`,
> both API-stable, and the newer versions are verified working here. APScheduler
> 3.6.3 in particular is *broken* with `tzlocal>=3` — it raises
> `TypeError: Only timezones from the pytz library are supported` for any job on
> a default-timezone scheduler. Install those two with `--no-deps` so pip does
> not drag them back down:
> ```bash
> pip install -r requirements.txt
> pip install --upgrade --no-deps APScheduler==3.11.3 cachetools==7.1.7
> ```


**Getting Started:**

1. Clone the repository: `git clone https://github.com/firmanelhakim/praypalbot.git`
2. Create a virtualenv and install dependencies:
   ```bash
   python3 -m venv env && source env/bin/activate && pip install -r requirements.txt
   ```
3. Configure secrets:
   ```bash
   cp .env.example .env   # then edit .env and add your bot token
   chmod 600 .env
   ```
   Only `TELEGRAM_BOT_TOKEN` is required. The email settings are optional — if
   they are unset, error alerts are logged and skipped rather than raising.
   The AlAdhan prayer-times API requires no API key.
4. Run the bot: `./run.sh` (start), `./run.sh stop`, `./run.sh restart`
   **OR** run directly with `python3 main.py`.

The SQLite database is created automatically on first run; you do not need to
create `praypalbot.db` yourself.

**Running the tests:**

```bash
TELEGRAM_BOT_TOKEN=dummy PRAYPALBOT_LOG=/tmp/praypalbot-test.log \
    python -m unittest discover -v
```

29 tests, no network access required. `PRAYPALBOT_LOG` keeps the suite's output
out of the live `praypalbot.log` — `utils.py` configures logging at import time,
so without it the test fixtures (chat 4242, "Nowhereville") land in the real log.
`PRAYPALBOT_DB` overrides the database path the same way.

**Security Considerations:**

* Secrets live in `.env`, which is gitignored — **never commit it**. `credentials.py`
  reads from the environment and is safe to commit.
* `praypalbot.db` (user chat IDs and locations) and `praypalbot.log` (which has
  historically contained the bot token) are gitignored. Keep them out of the repo.
* Use a Google **app password**, not your account password, for email alerts.
* If a token is ever exposed, rotate it via @BotFather — revocation is the only
  real remedy.

**Operational notes:**

* `praypalbot.log` grows unbounded. A sample `logrotate` config is provided in
  `praypalbot.logrotate`.
* Prayer times and DST offsets are refreshed daily by a midnight-UTC cron job,
  and on startup.

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

