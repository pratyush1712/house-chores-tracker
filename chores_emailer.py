"""
chores_emailer.py
=================
CLI script for sending house chore reminder emails via Gmail SMTP.

Usage:
  python chores_emailer.py monday   # Send Monday kick-off emails + seed DB
  python chores_emailer.py sunday   # Send Sunday check-in emails

Environment variables (set in .env or as repo secrets):
  SMTP_USERNAME   — Gmail address used to send
  SMTP_PASSWORD   — Gmail App Password (16-char, no spaces)
  UPSTASH_REDIS_REST_URL    — Upstash Redis REST endpoint (optional)
  UPSTASH_REDIS_REST_TOKEN  — Upstash Redis REST token (optional)
"""

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

from lib.chores import (
    CHORE_ICONS,
    HOUSEMATES,
    get_rotation_week,
    get_week_number,
    get_week_schedule,
)
from lib.db import get_task_status, seed_week

# ── SMTP config ────────────────────────────────────────────────────────────────

GMAIL_USER: str     = os.getenv("SMTP_USERNAME", "")
GMAIL_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

_TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_template(filename: str, replacements: dict[str, str]) -> str:
    """Reads an HTML template and substitutes {{KEY}} placeholders."""
    path = os.path.join(_TEMPLATE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def _send_email(to_email: str, subject: str, html_body: str) -> None:
    """Sends a single HTML email via Gmail SMTP-SSL."""
    if not GMAIL_USER or not GMAIL_PASSWORD:
        raise RuntimeError(
            "SMTP_USERNAME and SMTP_PASSWORD must be set in environment variables."
        )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())
    print(f"  Sent → {to_email}")


# ── Monday ────────────────────────────────────────────────────────────────────

def send_monday_reminders() -> None:
    """
    Sends each housemate their Monday kick-off email and pre-populates
    the database with 'pending' records for every task this week.
    """
    week_abs = get_week_number()
    week_num = get_rotation_week(week_abs)
    schedule = get_week_schedule(week_abs)

    print(f"\nSending Monday reminders — Rotation Week {week_num} (abs {week_abs})...")

    for name, chores in schedule.items():
        main_chores = [c for c in chores if c != "Hallways"]
        if not main_chores:
            continue
        chore = main_chores[0]
        person_info = HOUSEMATES[name]

        html = _load_template("email_monday.html", {
            "NAME":       name,
            "WEEK_NUM":   str(week_num),
            "CHORE_ICON": CHORE_ICONS[chore],
            "CHORE_NAME": chore,
        })
        subject = f"Chores — Week {week_num}, you've got {chore}, {name}"
        _send_email(person_info["email"], subject, html)

    # Pre-populate the database so the dashboard shows all tasks immediately.
    seed_week(week_abs, schedule)
    print(f"  Database seeded for week {week_abs}.")


# ── Sunday ────────────────────────────────────────────────────────────────────

def send_sunday_reminders() -> None:
    """
    Sends each housemate a Sunday check-in email. If Redis is configured,
    reads the current completion status to personalise the subject line.
    """
    week_abs = get_week_number()
    week_num = get_rotation_week(week_abs)
    schedule = get_week_schedule(week_abs)

    print(f"\nSending Sunday check-ins — Rotation Week {week_num} (abs {week_abs})...")

    for name, chores in schedule.items():
        main_chores = [c for c in chores if c != "Hallways"]
        if not main_chores:
            continue
        chore = main_chores[0]
        person_info = HOUSEMATES[name]

        # Personalise subject based on completion status (if DB available).
        status = get_task_status(week_abs, name, chore)
        if status == "done":
            subject = f"Week {week_num} wrap-up — nice work, {name}!"
        else:
            subject = f"Week {week_num} check-in — did {chore} happen, {name}?"

        html = _load_template("email_sunday.html", {
            "NAME":       name,
            "WEEK_NUM":   str(week_num),
            "CHORE_ICON": CHORE_ICONS[chore],
            "CHORE_NAME": chore,
        })
        _send_email(person_info["email"], subject, html)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if mode == "monday":
        send_monday_reminders()
    elif mode == "sunday":
        send_sunday_reminders()
    else:
        print("Usage: python chores_emailer.py [monday|sunday]")
        sys.exit(1)
