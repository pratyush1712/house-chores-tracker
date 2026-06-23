# ruff: noqa: E402
import sys
import unittest
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.chores import get_rotation_week, get_week_number, get_week_schedule


class WeekBoundaryTests(unittest.TestCase):
    """Chore weeks run Tuesday -> Monday, so the week index must only roll
    over on Tuesday. The closing Monday belongs to the week ending that night,
    not the week that starts the next day."""

    def test_week_rolls_over_on_tuesday_not_monday(self) -> None:
        # Week 6 runs Tue Jun 16 -> Mon Jun 22; week 7 runs Tue Jun 23 -> Mon Jun 29.
        self.assertEqual(get_week_number(date(2026, 6, 16)), 6)  # Tuesday start
        self.assertEqual(get_week_number(date(2026, 6, 22)), 6)  # closing Monday
        self.assertEqual(get_week_number(date(2026, 6, 23)), 7)  # next Tuesday
        self.assertEqual(get_week_number(date(2026, 6, 29)), 7)  # closing Monday

    def test_monday_checkin_targets_the_ending_week(self) -> None:
        # On the Monday that closes week 6, the rotation number is 3 (not 4) and
        # Pratyush is not on Trash, so he should receive no check-in.
        week_abs = get_week_number(date(2026, 6, 22))
        self.assertEqual(get_rotation_week(week_abs), 3)
        self.assertNotIn("Trash", get_week_schedule(week_abs)["Pratyush"])

    def test_clamps_to_zero_before_first_week(self) -> None:
        self.assertEqual(get_week_number(date(2026, 5, 4)), 0)
        self.assertEqual(get_week_number(date(2026, 5, 5)), 0)
        self.assertEqual(get_week_number(date(2026, 5, 12)), 1)


if __name__ == "__main__":
    unittest.main()
