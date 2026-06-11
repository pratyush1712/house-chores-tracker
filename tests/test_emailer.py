# ruff: noqa: E402
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from lib import emailer


class ReminderEmailTests(unittest.TestCase):
    def test_tuesday_email_includes_every_assigned_chore_once(self) -> None:
        sent: list[tuple[list[str], str, str, str]] = []
        schedule = {"Juan": ["Kitchen", "Trash", "Hallways"]}

        with (
            patch.object(emailer, "get_week_number", return_value=0),
            patch.object(emailer, "get_week_schedule", return_value=schedule),
            patch.object(emailer, "seed_week"),
            patch.object(
                emailer,
                "_send_email",
                side_effect=lambda *args: sent.append(args),
            ),
        ):
            emailer.send_reminders("tuesday")

        self.assertEqual(len(sent), 1)
        recipients, subject, html, text = sent[0]
        self.assertEqual(recipients, ["jpc343@cornell.edu"])
        self.assertIn("Kitchen, Trash and Hallways", subject)
        self.assertIn("Kitchen", html)
        self.assertIn("Trash", html)
        self.assertIn("Hallways", html)
        self.assertIn("- Kitchen", text)
        self.assertIn("- Trash", text)
        self.assertIn("- Hallways", text)
        self.assertNotIn("Shared chore", html)
        self.assertNotIn("Shared chore", text)
        self.assertNotIn("{{", html)

    def test_monday_email_summarizes_pending_chores(self) -> None:
        sent: list[tuple[list[str], str, str, str]] = []
        schedule = {"Juan": ["Kitchen", "Hallways"]}

        def status(_week_abs: int, _name: str, chore: str) -> str:
            return "done" if chore == "Kitchen" else "pending"

        with (
            patch.object(emailer, "get_week_number", return_value=0),
            patch.object(emailer, "get_week_schedule", return_value=schedule),
            patch.object(emailer, "get_task_status", side_effect=status),
            patch.object(
                emailer,
                "_send_email",
                side_effect=lambda *args: sent.append(args),
            ),
        ):
            emailer.send_reminders("monday")

        self.assertEqual(len(sent), 1)
        _recipients, subject, html, text = sent[0]
        self.assertIn("1 chore to update", subject)
        self.assertIn("Still needs an update: Hallways.", html)
        self.assertIn("Done", html)
        self.assertIn("Needs update", html)
        self.assertIn("- Kitchen", text)
        self.assertIn("- Hallways", text)
        self.assertNotIn("Shared chore", html)
        self.assertNotIn("Shared chore", text)
        self.assertNotIn("{{", html)

    def test_preview_writes_html_without_sending_email(self) -> None:
        schedule = {"Juan": ["Kitchen", "Hallways"]}

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(emailer, "get_week_number", return_value=0),
                patch.object(emailer, "get_week_schedule", return_value=schedule),
                patch.object(emailer, "_send_email") as send_email,
            ):
                previews = emailer.preview_reminders("tuesday", tmpdir)

            send_email.assert_not_called()
            self.assertEqual(len(previews), 1)
            self.assertIn("Kitchen and Hallways", previews[0]["subject"])
            preview_path = Path(tmpdir) / "week-1-tuesday-juan.html"
            self.assertTrue(preview_path.exists())
            html = preview_path.read_text(encoding="utf-8")
            self.assertIn("PaperOps / House Chores", html)
            self.assertIn("Kitchen", html)
            self.assertIn("Hallways", html)
            self.assertNotIn("{{", html)


if __name__ == "__main__":
    unittest.main()
