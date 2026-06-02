from datetime import date, datetime
from zoneinfo import ZoneInfo
import unittest

from lib.chores import get_rotation_week, get_week_number, get_week_schedule
from lib.db import _is_on_time


class RotationBoundaryTest(unittest.TestCase):
    def test_week_rolls_over_on_tuesday_not_monday(self) -> None:
        self.assertEqual(get_week_number(date(2026, 6, 1)), 3)
        self.assertEqual(get_rotation_week(3), 4)
        self.assertIn("Trash", get_week_schedule(3)["Pratyush"])

        self.assertEqual(get_week_number(date(2026, 6, 2)), 4)
        self.assertEqual(get_rotation_week(4), 1)
        self.assertIn("Bathroom", get_week_schedule(4)["Pratyush"])

    def test_monday_due_date_counts_as_on_time(self) -> None:
        marked_monday = datetime(2026, 6, 1, 20, 0, tzinfo=ZoneInfo("America/New_York"))
        marked_tuesday = datetime(2026, 6, 2, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        self.assertTrue(_is_on_time(3, marked_monday, date(2026, 5, 4)))
        self.assertFalse(_is_on_time(3, marked_tuesday, date(2026, 5, 4)))


if __name__ == "__main__":
    unittest.main()
