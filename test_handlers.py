"""Tests for the Telegram command handlers and reminder scheduling.

    TELEGRAM_BOT_TOKEN=dummy PRAYPALBOT_LOG=/tmp/praypalbot-test.log \
        ./env/bin/python -m unittest discover -v

Covers lead-time validation, MarkdownV2 escaping, and reading job data from
the job context rather than the job name.
"""

import datetime
import unittest
from unittest import mock

import pytz

import command_handler
import reminders
from config import INACTIVE_LEAD_TIME
from telegram.ext import ConversationHandler


def _make_update(text):
    """Builds a minimal Update stand-in that records replies."""
    update = mock.Mock()
    update.message.text = text
    update.message.chat_id = 4242
    update.message.replies = []
    update.message.reply_text.side_effect = (
        lambda *a, **k: update.message.replies.append(a[0])
    )
    return update


class LeadTimeValidationTests(unittest.TestCase):
    def setUp(self):
        self.context = mock.Mock()
        patcher = mock.patch.object(
            command_handler, "get_user_settings", return_value=("Singapore", None)
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        save = mock.patch.object(command_handler, "save_user_settings")
        self.addCleanup(save.stop)
        self.save = save.start()
        sched = mock.patch.object(command_handler, "schedule_prayer_times")
        self.addCleanup(sched.stop)
        self.schedule = sched.start()

    def test_negative_one_is_rejected(self):
        """-1 collides with the inactive sentinel and used to mute a user forever."""
        update = _make_update("-1")
        state = command_handler.lead_time_handler(update, self.context)

        self.assertEqual(state, command_handler.SET_LEAD_TIME, "must re-prompt")
        self.save.assert_not_called()
        self.assertIn("between", update.message.replies[0])

    def test_other_negatives_are_rejected(self):
        for text in ("-5", "-30", "-1440"):
            with self.subTest(text=text):
                update = _make_update(text)
                state = command_handler.lead_time_handler(update, self.context)
                self.assertEqual(state, command_handler.SET_LEAD_TIME)

    def test_absurdly_large_value_is_rejected(self):
        update = _make_update("99999")
        state = command_handler.lead_time_handler(update, self.context)
        self.assertEqual(state, command_handler.SET_LEAD_TIME)

    def test_zero_is_stored_as_no_lead_time(self):
        update = _make_update("0")
        state = command_handler.lead_time_handler(update, self.context)
        self.assertEqual(state, ConversationHandler.END)
        self.save.assert_called_once_with(4242, "Singapore", None)

    def test_valid_lead_time_is_saved(self):
        update = _make_update("15")
        state = command_handler.lead_time_handler(update, self.context)
        self.assertEqual(state, ConversationHandler.END)
        self.save.assert_called_once_with(4242, "Singapore", 15)

    def test_skip_sets_none(self):
        update = _make_update("SKIP")
        state = command_handler.lead_time_handler(update, self.context)
        self.assertEqual(state, ConversationHandler.END)
        self.save.assert_called_once_with(4242, "Singapore", None)

    def test_non_numeric_re_prompts(self):
        update = _make_update("soon please")
        state = command_handler.lead_time_handler(update, self.context)
        self.assertEqual(state, command_handler.SET_LEAD_TIME)
        self.save.assert_not_called()

    def test_missing_settings_ends_conversation_with_a_reply(self):
        """Previously returned None, leaving the user with no response."""
        with mock.patch.object(command_handler, "get_user_settings", return_value=None):
            update = _make_update("10")
            state = command_handler.lead_time_handler(update, self.context)
        self.assertEqual(state, ConversationHandler.END)
        self.assertTrue(update.message.replies, "user must get a reply")


class LocationValidationTests(unittest.TestCase):
    def setUp(self):
        save = mock.patch.object(command_handler, "save_user_settings")
        self.addCleanup(save.stop)
        self.save = save.start()
        sched = mock.patch.object(command_handler, "schedule_prayer_times")
        self.addCleanup(sched.stop)
        sched.start()
        self.context = mock.Mock()

    def test_overlong_location_is_rejected(self):
        update = _make_update("x" * 500)
        state = command_handler.location_handler(update, self.context)
        self.assertEqual(state, command_handler.SET_LOCATION)
        self.save.assert_not_called()

    def test_non_latin_location_capitalization_is_preserved(self):
        """.title() used to mangle these; the user's own text is kept."""
        update = _make_update("  دمشق  ")
        command_handler.location_handler(update, self.context)
        self.save.assert_called_once_with(4242, "دمشق", None)

    def test_internal_whitespace_is_collapsed(self):
        update = _make_update("El Oued   Algeria")
        command_handler.location_handler(update, self.context)
        self.save.assert_called_once_with(4242, "El Oued Algeria", None)


class MarkdownEscapingTests(unittest.TestCase):
    def test_location_with_reserved_chars_is_escaped(self):
        """'Cairo - Egypt' previously made Telegram reject the whole message."""
        update = _make_update("/todayprayertimes")
        context = mock.Mock()
        today = datetime.datetime.now(pytz.utc).date().strftime("%Y-%m-%d")
        response = {
            "prayer_times": [{"date_for": today, "fajr": "05:45", "dhuhr": "13:10"}],
            "timezone": "Africa/Cairo",
        }

        with mock.patch.object(
            command_handler, "get_user_settings", return_value=("Cairo - Egypt", 10)
        ), mock.patch.object(
            command_handler, "get_prayer_times", return_value=response
        ):
            command_handler.today_prayer_times(update, context)

        context.bot.send_message.assert_called_once()
        sent_text = context.bot.send_message.call_args.kwargs["text"]
        self.assertIn(r"Cairo \- Egypt", sent_text, "hyphen must be escaped")
        self.assertEqual(
            context.bot.send_message.call_args.kwargs["parse_mode"], "MarkdownV2"
        )


class UpcomingReminderTests(unittest.TestCase):
    """/nextsalat must read job context, not parse the job name."""

    def _job_queue(self, jobs):
        job_queue = mock.Mock()
        job_queue.scheduler.get_jobs.return_value = jobs
        return job_queue

    def _aps_job(self, name, run_at, context):
        ptb_job = mock.Mock()
        ptb_job.context = context
        callback_context = mock.Mock()
        callback_context.job = ptb_job

        aps_job = mock.Mock()
        aps_job.name = name
        aps_job.next_run_time = run_at
        aps_job.args = (callback_context,)
        return aps_job

    def test_reads_prayer_name_and_timezone_from_context(self):
        run_at = datetime.datetime.now(pytz.utc) + datetime.timedelta(hours=2)
        job = self._aps_job(
            "4242_maghrib_2026-08-07_uuid_exact",
            run_at,
            {
                "chat_id": 4242,
                "prayer_name": "maghrib",
                "lead_time": None,
                "timezone": "Asia/Kolkata",
            },
        )
        result = reminders.get_upcoming_reminder(4242, self._job_queue([job]))

        self.assertEqual(result["prayer_name"], "maghrib")
        self.assertIn("IST", result["scheduled_time"], "shown in the user's timezone")
        self.assertIn("hour", result["time_remaining"])

    def test_lead_time_job_can_be_the_next_reminder(self):
        """Lead jobs were previously filtered out, hiding the true next reminder."""
        now = datetime.datetime.now(pytz.utc)
        lead = self._aps_job(
            "4242_isha_2026-08-07_uuid_lead",
            now + datetime.timedelta(minutes=30),
            {
                "chat_id": 4242,
                "prayer_name": "isha",
                "lead_time": 10,
                "timezone": "UTC",
            },
        )
        exact = self._aps_job(
            "4242_isha_2026-08-07_uuid_exact",
            now + datetime.timedelta(minutes=40),
            {
                "chat_id": 4242,
                "prayer_name": "isha",
                "lead_time": None,
                "timezone": "UTC",
            },
        )
        result = reminders.get_upcoming_reminder(4242, self._job_queue([exact, lead]))
        self.assertEqual(result["lead_time"], 10, "the earlier lead job should win")

    def test_returns_none_without_jobs(self):
        self.assertIsNone(reminders.get_upcoming_reminder(4242, self._job_queue([])))

    def test_ignores_other_users_jobs(self):
        job = self._aps_job(
            "9999_fajr_2026-08-07_uuid_exact",
            datetime.datetime.now(pytz.utc) + datetime.timedelta(hours=1),
            {"chat_id": 9999, "prayer_name": "fajr", "timezone": "UTC"},
        )
        self.assertIsNone(reminders.get_upcoming_reminder(4242, self._job_queue([job])))


class DeactivatedUserTests(unittest.TestCase):
    def test_inactive_user_is_skipped(self):
        job_queue = mock.Mock()
        with mock.patch.object(reminders, "get_prayer_times") as fetch:
            reminders.schedule_prayer_times(
                chat_id=4242,
                location="Singapore",
                lead_time=INACTIVE_LEAD_TIME,
                job_queue=job_queue,
            )
        fetch.assert_not_called()
        job_queue.run_once.assert_not_called()


class SchedulingTests(unittest.TestCase):
    def test_past_prayers_are_skipped_and_future_ones_scheduled(self):
        # Build the window from a fixed local instant so the test doesn't
        # depend on the wall-clock hour it happens to run at (a "+3 hours"
        # offset late in the evening rolls onto the next calendar day).
        sg = pytz.timezone("Asia/Singapore")
        now_sg = datetime.datetime.now(sg)
        future_local = now_sg + datetime.timedelta(hours=3)
        response = {
            "prayer_times": [
                {
                    "date_for": now_sg.strftime("%Y-%m-%d"),
                    "past": "00:01",
                },
                {
                    "date_for": future_local.strftime("%Y-%m-%d"),
                    "future": future_local.strftime("%H:%M"),
                },
            ],
            "timezone": "Asia/Singapore",
        }
        job_queue = mock.Mock()
        job_queue.scheduler.get_jobs.return_value = []
        with mock.patch.object(reminders, "get_prayer_times", return_value=response):
            reminders.schedule_prayer_times(4242, "Singapore", None, job_queue)

        scheduled = [
            c.kwargs["context"]["prayer_name"]
            for c in job_queue.run_once.call_args_list
        ]
        self.assertIn("future", scheduled)
        self.assertNotIn("past", scheduled)

    def test_api_failure_schedules_nothing(self):
        job_queue = mock.Mock()
        with mock.patch.object(
            reminders, "get_prayer_times", return_value="Service unavailable"
        ):
            reminders.schedule_prayer_times(4242, "Singapore", None, job_queue)
        job_queue.run_once.assert_not_called()


if __name__ == "__main__":
    unittest.main()
