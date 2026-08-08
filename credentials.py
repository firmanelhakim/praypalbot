"""Configuration loaded from the environment.

Secrets are read from environment variables, falling back to a local `.env`
file (gitignored). Nothing sensitive is stored in this file — see
`.env.example` for the template.
"""

import os

from config import get_file_path


def _load_dotenv(path=None):
    """Loads KEY=VALUE pairs from `.env` into os.environ.

    Minimal on purpose, to keep the project free of extra dependencies. Real
    environment variables always win, and a missing file is not an error.
    """
    path = path or get_file_path(".env")
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _require(name):
    """Returns a required setting, failing fast with an actionable message."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            f"Copy .env.example to .env and fill it in, or export {name}."
        )
    return value


# Required: the bot cannot run without a token.
TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")

# Optional: error-alert email. When unset, send_email() no-ops with a warning
# rather than raising, so a missing mail config never takes the bot down.
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")
RECIPIENTS = os.environ.get("RECIPIENTS", "")
