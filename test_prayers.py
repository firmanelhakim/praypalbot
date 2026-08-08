"""Tests for prayer-times parsing and timezone handling.

    TELEGRAM_BOT_TOKEN=dummy PRAYPALBOT_LOG=/tmp/praypalbot-test.log \
        ./env/bin/python -m unittest discover -v

PRAYPALBOT_LOG keeps test output out of the live praypalbot.log — importing
utils.py configures logging at import time.

No network: the AlAdhan API is stubbed.
"""

import datetime
import unittest
from unittest import mock

import pytz

import prayers
import reminders
from utils import normalize_location, prayer_time_cache


def _aladhan_day(date_ddmmyyyy, timezone="Asia/Singapore", fajr="05:45 (+08)"):
    """Builds one day of an AlAdhan calendar response."""
    return {
        "timings": {
            "Fajr": fajr,
            "Sunrise": "07:05 (+08)",
            "Dhuhr": "13:10 (+08)",
            "Asr": "16:33 (+08)",
            "Maghrib": "19:15 (+08)",
            "Isha": "20:29 (+08)",
        },
        "date": {"gregorian": {"date": date_ddmmyyyy}},
        "meta": {"timezone": timezone},
    }


class TimezoneHandlingTests(unittest.TestCase):
    """Half-hour zones and DST — the audit's highest-impact bug."""

    def test_localize_preserves_half_hour_offsets(self):
        naive = datetime.datetime(2026, 8, 7, 5, 45)
        cases = {
            "Asia/Kolkata": datetime.timedelta(hours=5, minutes=30),
            "Asia/Kathmandu": datetime.timedelta(hours=5, minutes=45),
            "Asia/Tehran": datetime.timedelta(hours=3, minutes=30),
            "Asia/Singapore": datetime.timedelta(hours=8),
        }
        for name, expected in cases.items():
            with self.subTest(timezone=name):
                aware = reminders._localize(naive, pytz.timezone(name))
                self.assertEqual(aware.utcoffset(), expected)
                # Wall-clock time must be preserved exactly.
                self.assertEqual((aware.hour, aware.minute), (5, 45))

    def test_localize_follows_dst_transition(self):
        london = pytz.timezone("Europe/London")
        summer = reminders._localize(datetime.datetime(2026, 8, 7, 5, 45), london)
        winter = reminders._localize(datetime.datetime(2026, 12, 7, 5, 45), london)
        self.assertEqual(summer.utcoffset(), datetime.timedelta(hours=1))
        self.assertEqual(winter.utcoffset(), datetime.timedelta(0))

    def test_localize_handles_nonexistent_wallclock(self):
        """Spring-forward gap must not raise."""
        london = pytz.timezone("Europe/London")
        # 2026-03-29 01:30 does not exist in Europe/London.
        aware = reminders._localize(datetime.datetime(2026, 3, 29, 1, 30), london)
        self.assertIsNotNone(aware.tzinfo)


class GetPrayerTimesTests(unittest.TestCase):
    def setUp(self):
        prayer_time_cache.clear()

    def test_parses_calendar_and_returns_timezone_name(self):
        payload = {
            "code": 200,
            "data": [_aladhan_day("07-08-2026"), _aladhan_day("08-08-2026")],
        }
        with mock.patch.object(prayers, "_fetch_calendar", return_value=payload):
            result = prayers.get_prayer_times("Singapore")

        self.assertIsInstance(result, dict)
        self.assertEqual(result["timezone"], "Asia/Singapore")
        self.assertEqual(len(result["prayer_times"]), 2)

        first = result["prayer_times"][0]
        self.assertEqual(first["date_for"], "2026-08-07")  # DD-MM-YYYY -> YYYY-MM-DD
        self.assertEqual(first["fajr"], "05:45")  # "(+08)" annotation stripped
        self.assertEqual(first["shurooq"], "07:05")  # Sunrise -> shurooq

    def test_api_error_message_is_returned(self):
        payload = {"code": 400, "data": "Unable to geocode"}
        with mock.patch.object(prayers, "_fetch_calendar", return_value=payload):
            self.assertEqual(
                prayers.get_prayer_times("Nowhereville"), "Unable to geocode"
            )

    def test_unusable_timezone_falls_back_to_utc(self):
        payload = {
            "code": 200,
            "data": [_aladhan_day("07-08-2026", timezone="Bad/Zone")],
        }
        with mock.patch.object(prayers, "_fetch_calendar", return_value=payload):
            result = prayers.get_prayer_times("Somewhere")
        self.assertEqual(result["timezone"], "UTC")

    def test_cache_key_is_normalized(self):
        payload = {"code": 200, "data": [_aladhan_day("07-08-2026")]}
        with mock.patch.object(
            prayers, "_fetch_calendar", return_value=payload
        ) as fetch:
            prayers.get_prayer_times("Singapore")
            prayers.get_prayer_times("  singapore ")  # same place, different spelling
        self.assertEqual(
            fetch.call_count, 1, "case/space variants must share a cache entry"
        )

    def test_fetch_retries_transient_failures(self):
        from requests.exceptions import RequestException

        payload = {"code": 200, "data": [_aladhan_day("07-08-2026")]}
        responses = [RequestException("boom"), RequestException("boom again"), payload]

        def fake_get(url, params=None, timeout=None):
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = item
            return response

        with mock.patch.object(
            prayers.requests, "get", side_effect=fake_get
        ), mock.patch.object(
            prayers.time, "sleep"
        ):  # don't actually back off
            result = prayers.get_prayer_times("Singapore")

        self.assertIsInstance(result, dict, "should succeed on the third attempt")

    def test_gives_up_after_max_attempts(self):
        from requests.exceptions import RequestException

        with mock.patch.object(
            prayers.requests, "get", side_effect=RequestException("down")
        ) as get, mock.patch.object(prayers.time, "sleep"):
            result = prayers.get_prayer_times("Singapore")

        self.assertIsInstance(
            result, str, "persistent failure returns an error message"
        )
        self.assertEqual(get.call_count, prayers.MAX_FETCH_ATTEMPTS)


class NormalizeLocationTests(unittest.TestCase):
    def test_collapses_case_and_whitespace(self):
        self.assertEqual(normalize_location("  Kuala   Lumpur "), "kuala lumpur")
        self.assertEqual(normalize_location("SINGAPORE"), "singapore")
        self.assertEqual(normalize_location(None), "")


if __name__ == "__main__":
    unittest.main()
