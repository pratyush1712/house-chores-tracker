# ruff: noqa: E402
"""
chores_emailer.py
=================
CLI script for sending house chore reminder emails via SMTP (Gmail or any host).

Environment variables (see .env.example):
  SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL
  Connection: either SMTP_PORT + SMTP_USE_STARTTLS,
  or Private Email style SMTP_PORT_SSL / SMTP_PORT_TLS (when both set, 465+SSL is used)

E402 is suppressed file-wide: load_dotenv() must run before lib.* imports so
that env vars (Redis credentials, SMTP) are present when the modules initialise.
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

SMTP_HOST: str = os.getenv("SMTP_HOST") or "smtp.gmail.com"
SMTP_LOGIN: str = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM: str = os.getenv("SMTP_FROM_EMAIL", "") or SMTP_LOGIN


def _smtp_port_and_tls() -> tuple[int, bool]:
    """
    Resolve port and whether to use STARTTLS.

    Priority:
      1. SMTP_PORT + SMTP_USE_STARTTLS (explicit; 587 implies STARTTLS if unset)
      2. SMTP_PORT_SSL only → implicit SSL (SMTP_SSL)
      3. SMTP_PORT_TLS only → STARTTLS (typical 587)
      4. Both Private Email vars → prefer 465 + SSL
      5. Default 465 + SSL
    """
    port_raw = os.getenv("SMTP_PORT")
    if port_raw is not None and port_raw.strip() != "":
        try:
            port = int(port_raw)
        except ValueError:
            port = 465
        starttls = os.getenv("SMTP_USE_STARTTLS", "").lower() in ("1", "true", "yes")
        if port == 587 and os.getenv("SMTP_USE_STARTTLS", "") == "":
            starttls = True
        return port, starttls

    ssl_raw = os.getenv("SMTP_PORT_SSL")
    tls_raw = os.getenv("SMTP_PORT_TLS")

    if ssl_raw and tls_raw:
        try:
            return int(ssl_raw), False
        except ValueError:
            pass
    if ssl_raw and not tls_raw:
        try:
            return int(ssl_raw), False
        except ValueError:
            pass
    if tls_raw and not ssl_raw:
        try:
            return int(tls_raw), True
        except ValueError:
            pass
    return 465, False


SMTP_PORT, SMTP_USE_STARTTLS = _smtp_port_and_tls()

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
    """Sends HTML via SMTP_SSL (port 465) or SMTP + STARTTLS (e.g. port 587)."""
    if not SMTP_LOGIN or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_USERNAME and SMTP_PASSWORD must be set in environment variables."
        )
    if not SMTP_FROM:
        raise RuntimeError("SMTP_FROM_EMAIL or SMTP_USERNAME must be set for the From address.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    payload = msg.as_string()

    if SMTP_USE_STARTTLS:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, payload)
    else:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_LOGIN, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, payload)
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

        html = _load_template(
            "email_monday.html",
            {
                "NAME": name,
                "WEEK_NUM": str(week_num),
                "CHORE_ICON": CHORE_ICONS[chore],
                "CHORE_NAME": chore,
            },
        )
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

        html = _load_template(
            "email_sunday.html",
            {
                "NAME": name,
                "WEEK_NUM": str(week_num),
                "CHORE_ICON": CHORE_ICONS[chore],
                "CHORE_NAME": chore,
            },
        )
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
