"""Standard crontab rules used by both the preview API and reminder worker."""
import importlib
import importlib.util
import unittest
from datetime import datetime


class TodoCronTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.core.todo_cron"), "Todo cron scheduling is missing")
        self.cron = importlib.import_module("app.core.todo_cron")

    def times(self, expression, after, count=5, zone="Asia/Shanghai"):
        return [date.isoformat() for date in self.cron.cron_occurrences(
            expression, zone, after=datetime.fromisoformat(after), count=count,
        )]

    def test_normalizes_whitespace_and_standard_named_fields(self):
        self.assertEqual(self.cron.normalize_cron("  0  9-17/2 * jan,mar mon-fri  "), "0 9-17/2 * JAN,MAR MON-FRI")

    def test_intervals_are_minute_granular_and_strictly_after_the_start(self):
        self.assertEqual(self.times("*/15 * * * *", "2026-11-17T04:00:00Z", 3), [
            "2026-11-17T12:15:00+08:00", "2026-11-17T12:30:00+08:00", "2026-11-17T12:45:00+08:00",
        ])
        self.assertEqual(self.times("*/60 * * * *", "2026-11-17T04:00:00Z", 1), ["2026-11-17T13:00:00+08:00"])

    def test_weekday_rules_use_the_saved_timezone(self):
        self.assertEqual(self.times("0 9 * * MON-FRI", "2026-11-17T04:00:00Z", 2), [
            "2026-11-18T09:00:00+08:00", "2026-11-19T09:00:00+08:00",
        ])
        self.assertEqual(self.times("0 9 * * 0,6", "2026-11-17T04:00:00Z", 2), [
            "2026-11-21T09:00:00+08:00", "2026-11-22T09:00:00+08:00",
        ])

    def test_day_of_month_and_weekday_have_standard_or_semantics(self):
        self.assertEqual(self.times("0 9 1 * MON", "2026-11-17T04:00:00Z", 3), [
            "2026-11-23T09:00:00+08:00", "2026-11-30T09:00:00+08:00", "2026-12-01T09:00:00+08:00",
        ])

    def test_cron_skips_nonexistent_month_dates_instead_of_clamping(self):
        self.assertEqual(self.times("0 9 31 * *", "2026-01-31T09:00:00+08:00", 2), [
            "2026-03-31T09:00:00+08:00", "2026-05-31T09:00:00+08:00",
        ])
        self.assertEqual(self.times("0 9 29 2 *", "2024-03-01T00:00:00Z", 1), ["2028-02-29T09:00:00+08:00"])

    def test_invalid_extended_or_unreachable_expressions_are_rejected(self):
        for expression in ("", "@daily", "0 0 9 * * *", "60 9 * * *", "0 24 * * *", "*/0 * * * *",
                           "*/61 * * * *", "0 9 0 * *", "0 9 * 13 *", "0 9 * * 8", "0 9 * * FRI-MON",
                           "0 9 L * *", "0 9 * * MON#2", "0 9 ? * MON", "0 9 * * *\n", "0 9 * * *; rm",
                           "0 9 31 2 *", "0 9 30 2 *", "x" * 129):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.cron.normalize_cron(expression)
        # A weekday provides reachable dates even though February has no 31st.
        self.assertEqual(self.times("0 9 31 2 MON", "2026-01-31T00:00:00Z", 1), ["2026-02-02T09:00:00+08:00"])

    def test_dst_gap_uses_next_valid_clock_time_then_returns_to_original_rule(self):
        self.assertEqual(self.times("30 2 * * *", "2026-03-07T08:00:00Z", 2, "America/New_York"), [
            "2026-03-08T03:00:00-04:00", "2026-03-09T02:30:00-04:00",
        ])

    def test_fall_back_local_minute_is_not_scheduled_twice(self):
        self.assertEqual(self.times("30 1 * * *", "2026-11-01T05:30:00Z", 2, "America/New_York"), [
            "2026-11-02T01:30:00-05:00", "2026-11-03T01:30:00-05:00",
        ])

    def test_invalid_timezone_naive_start_or_unbounded_preview_is_rejected(self):
        for zone, after, count in (("Invalid/Zone", "2026-11-17T04:00:00Z", 5),
                                   ("Asia/Shanghai", "2026-11-17T04:00:00", 5),
                                   ("Asia/Shanghai", "2026-11-17T04:00:00Z", 0),
                                   ("Asia/Shanghai", "2026-11-17T04:00:00Z", 11)):
            with self.subTest(zone=zone, count=count), self.assertRaises(ValueError):
                self.times("0 9 * * *", after, count, zone)

    def test_next_time_uses_same_rule_as_preview(self):
        self.assertEqual(self.cron.next_cron_at(
            "0 9 * * MON-FRI", "Asia/Shanghai", after=datetime.fromisoformat("2026-11-20T09:00:00+08:00"),
        ), datetime.fromisoformat("2026-11-23T09:00:00+08:00"))


if __name__ == "__main__":
    unittest.main()
