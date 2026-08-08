import datetime
import logging
import re
import time
from json import JSONDecodeError

import pytz
import requests
from requests.exceptions import RequestException

from utils import normalize_location, prayer_time_cache

logger = logging.getLogger(__name__)

# Keyless and free. https://aladhan.com/prayer-times-api
ALADHAN_BASE_URL = "https://api.aladhan.com/v1"

# One failed request used to mean a user got no reminders at all for that run.
MAX_FETCH_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2

# AlAdhan timing keys -> the names the rest of the bot uses, in display order.
TIME_KEY_MAP = {
    "Fajr": "fajr",
    "Sunrise": "shurooq",
    "Dhuhr": "dhuhr",
    "Asr": "asr",
    "Maghrib": "maghrib",
    "Isha": "isha",
}


def _clean_time(value):
    """Strips the timezone annotation AlAdhan appends, e.g. "05:45 (+08)" -> "05:45"."""
    return re.sub(r"\s*\(.*\)$", "", value).strip()


def _fetch_calendar(url, params):
    """GETs the AlAdhan calendar endpoint, retrying transient failures.

    Returns the decoded payload, or re-raises the last exception.
    """
    last_error = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except (RequestException, JSONDecodeError) as exc:
            last_error = exc
            if attempt < MAX_FETCH_ATTEMPTS:
                delay = RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "AlAdhan fetch attempt %d/%d failed (%s); retrying in %ds",
                    attempt,
                    MAX_FETCH_ATTEMPTS,
                    exc,
                    delay,
                )
                time.sleep(delay)
    raise last_error


def get_prayer_times(location):
    """Fetches a week of prayer times for a location, with a 24h cache.

    Args:
        location (str): "City" or "City, Country".

    Returns:
        dict on success, or an error message string:
            {
                "prayer_times": [{"date_for": "YYYY-MM-DD", "fajr": "HH:MM", ...}, ...],
                "timezone": "Asia/Singapore",  # IANA name
            }
    """
    generic_error_message = (
        "Encountered an error while retrieving data. Please try again later."
    )

    # Normalized so case and spacing variants share one entry.
    cache_key = normalize_location(location)
    cached_data = prayer_time_cache.get(cache_key)
    if cached_data:
        return cached_data

    # AlAdhan wants city and country separately; the bot stores one free-text field.
    if "," in location:
        city, country = [part.strip() for part in location.split(",", 1)]
    else:
        city, country = location.strip(), ""

    # AlAdhan treats `from` as exclusive, so start a day early to include today.
    today = datetime.datetime.now(pytz.utc).date()
    start = today - datetime.timedelta(days=1)
    end = today + datetime.timedelta(days=6)
    start_str = start.strftime("%d-%m-%Y")
    end_str = end.strftime("%d-%m-%Y")

    params = {"city": city, "country": country}

    try:
        payload = _fetch_calendar(
            f"{ALADHAN_BASE_URL}/calendarByCity/from/{start_str}/to/{end_str}",
            params,
        )

        # Bad input comes back as code 400 with a string `data` message.
        if payload.get("code") != 200 or not isinstance(payload.get("data"), list):
            api_error = payload.get("data")
            logger.error("API error for location %r: %s", location, api_error)
            if isinstance(api_error, str) and api_error:
                return api_error
            return generic_error_message

        days = payload["data"]
        if not days:
            return generic_error_message

        prayer_times = []
        for day in days:
            timings = day.get("timings", {})
            gregorian_date = day.get("date", {}).get("gregorian", {}).get("date")
            if not gregorian_date:
                continue
            # DD-MM-YYYY -> YYYY-MM-DD.
            try:
                date_for = datetime.datetime.strptime(
                    gregorian_date, "%d-%m-%Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue

            entry = {"date_for": date_for}
            for aladhan_key, name in TIME_KEY_MAP.items():
                if aladhan_key in timings:
                    entry[name] = _clean_time(timings[aladhan_key])
            prayer_times.append(entry)

        if not prayer_times:
            return generic_error_message

        # The IANA name lets the scheduler do DST-aware, sub-hour-accurate math.
        timezone_name = days[0].get("meta", {}).get("timezone") or "UTC"
        try:
            pytz.timezone(timezone_name)
        except Exception:
            logger.warning(
                "AlAdhan returned unusable timezone %r for %r; falling back to UTC",
                timezone_name,
                location,
            )
            timezone_name = "UTC"

        result = {"prayer_times": prayer_times, "timezone": timezone_name}
        prayer_time_cache[cache_key] = result

        return result
    except RequestException as e:
        logger.error("Error getting prayer times for location %r: %s", location, e)
        return generic_error_message
    except JSONDecodeError as e:
        logger.error("Error decoding JSON response for location %r: %s", location, e)
        return generic_error_message
