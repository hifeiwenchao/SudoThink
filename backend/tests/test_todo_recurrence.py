"""Calendar scheduling keeps the original wall-clock rule without accumulating drift."""
import unittest
from datetime import datetime


class TodoRecurrenceTests(unittest.TestCase):
    def next_at(self, anchor, repeat, after, zone="Asia/Shanghai"):
        from app.core.todo_recurrence import next_reminder_at
        return next_reminder_at(
            datetime.fromisoformat(anchor), repeat, zone, after=datetime.fromisoformat(after),
        )

    def test_once_has_no_next_occurrence(self):
        self.assertIsNone(self.next_at("2026-11-17T12:00:00+08:00", "once", "2026-11-17T12:00:00+08:00"))

    def test_daily_skips_missed_dates_but_keeps_original_time(self):
        self.assertEqual(
            self.next_at("2026-11-17T12:30:00+08:00", "daily", "2026-11-23T08:00:00Z"),
            datetime.fromisoformat("2026-11-24T12:30:00+08:00"),
        )

    def test_next_occurrence_is_strictly_after_cutoff_and_not_before_anchor(self):
        self.assertEqual(
            self.next_at("2026-11-17T12:00:00+08:00", "daily", "2026-11-17T04:00:00Z"),
            datetime.fromisoformat("2026-11-18T12:00:00+08:00"),
        )
        self.assertEqual(
            self.next_at("2026-11-17T12:00:00+08:00", "daily", "2020-01-01T00:00:00Z"),
            datetime.fromisoformat("2026-11-17T12:00:00+08:00"),
        )

    def test_month_end_clamps_without_changing_the_original_day(self):
        for after, expected in (
            ("2026-01-31T09:15:00+08:00", "2026-02-28T09:15:00+08:00"),
            ("2026-02-28T09:15:00+08:00", "2026-03-31T09:15:00+08:00"),
            ("2026-12-31T09:15:00+08:00", "2027-01-31T09:15:00+08:00"),
        ):
            with self.subTest(after=after):
                self.assertEqual(self.next_at("2026-01-31T09:15:00+08:00", "monthly", after), datetime.fromisoformat(expected))

    def test_february_29_returns_to_leap_day_in_leap_year(self):
        for after, expected in (
            ("2024-02-29T18:00:00+08:00", "2025-02-28T18:00:00+08:00"),
            ("2027-02-28T18:00:00+08:00", "2028-02-29T18:00:00+08:00"),
        ):
            with self.subTest(after=after):
                self.assertEqual(self.next_at("2024-02-29T18:00:00+08:00", "yearly", after), datetime.fromisoformat(expected))

    def test_daily_retains_local_clock_across_daylight_saving(self):
        self.assertEqual(
            self.next_at("2026-03-07T09:00:00-05:00", "daily", "2026-03-07T15:00:00Z", "America/New_York"),
            datetime.fromisoformat("2026-03-08T09:00:00-04:00"),
        )

    def test_missing_local_time_moves_forward_by_dst_gap_for_that_day(self):
        self.assertEqual(
            self.next_at("2026-03-07T02:30:00-05:00", "daily", "2026-03-07T08:00:00Z", "America/New_York"),
            datetime.fromisoformat("2026-03-08T03:30:00-04:00"),
        )
        self.assertEqual(
            self.next_at("2026-03-07T02:30:00-05:00", "daily", "2026-03-08T08:00:00Z", "America/New_York"),
            datetime.fromisoformat("2026-03-09T02:30:00-04:00"),
        )

    def test_ambiguous_clock_only_schedules_first_occurrence(self):
        self.assertEqual(
            self.next_at("2026-10-31T01:30:00-04:00", "daily", "2026-11-01T05:30:00Z", "America/New_York"),
            datetime.fromisoformat("2026-11-02T01:30:00-05:00"),
        )


if __name__ == "__main__":
    unittest.main()
