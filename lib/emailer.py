# ruff: noqa: E402
"""
lib/emailer.py
==============
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
from email.utils import formataddr

from dotenv import load_dotenv

load_dotenv()

from lib.chores import (
    CHORE_ICONS,
    CHORE_META,
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

# ── Fallback SMTP config (Gmail App Password) ──────────────────────────────────
SMTP_FALLBACK_HOST: str = "smtp.gmail.com"
SMTP_FALLBACK_PORT: int = 587
SMTP_FALLBACK_LOGIN: str = os.getenv("SMTP_FALLBACK_USERNAME", "")
SMTP_FALLBACK_PASSWORD: str = os.getenv("SMTP_FALLBACK_PASSWORD", "")
SMTP_FALLBACK_FROM: str = (
    os.getenv("SMTP_FALLBACK_FROM_EMAIL", "") or SMTP_FALLBACK_LOGIN
)

_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_template(filename: str, replacements: dict[str, str]) -> str:
    """Reads an HTML template and substitutes {{KEY}} placeholders."""
    path = os.path.join(_TEMPLATE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def _attempt_smtp(
    host: str,
    port: int,
    use_starttls: bool,
    login: str,
    password: str,
    from_addr: str,
    to_emails: list[str],
    payload: str,
) -> None:
    """Low-level SMTP send - raises on any connection or auth failure."""
    if use_starttls:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(login, password)
            server.sendmail(from_addr, to_emails, payload)
    else:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(login, password)
            server.sendmail(from_addr, to_emails, payload)


def _send_email(
    to_emails: list[str], subject: str, html_body: str, text_body: str
) -> None:
    """
    Sends a multipart/alternative email (plain-text + HTML).
    Tries the primary SMTP first; falls back to Gmail if it fails.
    """
    if not SMTP_LOGIN or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_USERNAME and SMTP_PASSWORD must be set in environment variables."
        )
    if not SMTP_FROM:
        raise RuntimeError(
            "SMTP_FROM_EMAIL or SMTP_USERNAME must be set for the From address."
        )

    def _build_payload(from_addr: str) -> str:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr(("House Chores Tracker", from_addr))
        msg["To"] = ", ".join(to_emails)
        # Plain-text must come first; clients render the last supported part (HTML).
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        return msg.as_string()

    # ── Primary send ──────────────────────────────────────────────────────────
    primary_err: Exception | None = None
    try:
        _attempt_smtp(
            SMTP_HOST,
            SMTP_PORT,
            SMTP_USE_STARTTLS,
            SMTP_LOGIN,
            SMTP_PASSWORD,
            SMTP_FROM,
            to_emails,
            _build_payload(SMTP_FROM),
        )
        print(f"  Sent (primary) → {', '.join(to_emails)}")
        return
    except Exception as exc:
        primary_err = exc  # copy out - Python deletes 'exc' at end of except block

    # ── Fallback: Gmail ───────────────────────────────────────────────────────
    if not SMTP_FALLBACK_LOGIN or not SMTP_FALLBACK_PASSWORD:
        raise RuntimeError(
            f"Primary SMTP failed and no fallback configured: {primary_err}"
        )

    try:
        _attempt_smtp(
            SMTP_FALLBACK_HOST,
            SMTP_FALLBACK_PORT,
            True,
            SMTP_FALLBACK_LOGIN,
            SMTP_FALLBACK_PASSWORD,
            SMTP_FALLBACK_FROM,
            to_emails,
            _build_payload(SMTP_FALLBACK_FROM),
        )
        print(f"  Sent (fallback) → {', '.join(to_emails)}")
    except Exception as exc:
        raise RuntimeError(
            f"Both primary and fallback SMTP failed. Primary: {primary_err}. Fallback: {exc}"
        ) from exc


def send_reminders(mode: str) -> None:
    """
    Send chore reminder emails to all housemates.

    mode="tuesday" - kick-off email (email_tuesday.html); also seeds the DB.
    mode="monday"  - check-in email (email_monday.html); subject personalised
                     by current completion status.
    """
    if mode not in ("tuesday", "monday"):
        raise ValueError(f"mode must be 'tuesday' or 'monday', got {mode!r}")

    week_abs = get_week_number()
    week_num = get_rotation_week(week_abs)
    schedule = get_week_schedule(week_abs)
    template = f"email_{mode}.html"

    print(f"\nSending {mode} reminders - Week {week_num} (abs {week_abs})...")

    for name, chores in schedule.items():
        main_chores = [c for c in chores if not CHORE_META[c].get("shared")]
        if not main_chores:
            print(f"  Skipping {name} - no primary chore assigned this week.")
            continue
        chore = main_chores[0]
        person_info = HOUSEMATES[name]

        if mode == "tuesday":
            subject = f"Chores - Week {week_num}, you've got {chore}, {name}"
        else:
            status = get_task_status(week_abs, name, chore)
            if status == "done":
                subject = f"Week {week_num} wrap-up - nice work, {name}!"
            else:
                subject = f"Week {week_num} check-in - did {chore} happen, {name}?"

        html = _load_template(
            template,
            {
                "NAME": name,
                "WEEK_NUM": str(week_num),
                "CHORE_ICON": CHORE_ICONS[chore],
                "CHORE_NAME": chore,
            },
        )

        if mode == "tuesday":
            text = (
                f"Hi {name},\n\n"
                f"Your chore for Week {week_num}: {chore}\n"
                f"Complete it any day before Monday.\n\n"
                f"Shared chore (everyone): Hallways - quick sweep, every week.\n\n"
                f"No strict deadline, just get it done before the week is out.\n"
                f"If you need to swap, let the house know.\n\n"
                f"Track it here: https://autumn-legacy.site\n\n"
                f"-- House Chores Tracker"
            )
        else:
            text = (
                f"Hi {name},\n\n"
                f"Week {week_num} check-in - did {chore} get done?\n\n"
                f"Your chore: {chore}\n"
                f"Shared chore (everyone): Hallways\n\n"
                f"Update your status: https://autumn-legacy.site\n\n"
                f"If something came up, just let the house know. No drama.\n"
                f"New rotation starts Tuesday.\n\n"
                f"-- House Chores Tracker"
            )

        recipients = [str(person_info["email"])]
        if "email2" in person_info:
            recipients.append(str(person_info["email2"]))
        _send_email(recipients, subject, html, text)

    if mode == "tuesday":
        seed_week(week_abs, schedule)
        print(f"  Database seeded for week {week_abs}.")


def send_reminders_to_recipients(mode: str, recipient_names: list[str]) -> None:
    """
    Send chore reminder emails to specific housemates.

    mode="tuesday" - kick-off email (email_tuesday.html); also seeds the DB.
    mode="monday"  - check-in email (email_monday.html); subject personalised
                     by current completion status.
    recipient_names - list of housemate names to send emails to.
    """
    if mode not in ("tuesday", "monday"):
        raise ValueError(f"mode must be 'tuesday' or 'monday', got {mode!r}")

    if not recipient_names:
        raise ValueError("At least one recipient must be specified")

    week_abs = get_week_number()
    week_num = get_rotation_week(week_abs)
    schedule = get_week_schedule(week_abs)
    template = f"email_{mode}.html"

    valid_names = set(HOUSEMATES.keys())
    invalid_names = set(recipient_names) - valid_names
    if invalid_names:
        raise ValueError(f"Unknown recipients: {', '.join(invalid_names)}")

    print(f"\nSending {mode} reminders to specific recipients - Week {week_num} (abs {week_abs})...")

    for name in recipient_names:
        chores = schedule.get(name, [])
        main_chores = [c for c in chores if not CHORE_META[c].get("shared")]
        if not main_chores:
            print(f"  Skipping {name} - no primary chore assigned this week.")
            continue

        chore = main_chores[0]
        person_info = HOUSEMATES[name]

        if mode == "tuesday":
            subject = f"Chores - Week {week_num}, you've got {chore}, {name}"
        else:
            status = get_task_status(week_abs, name, chore)
            if status == "done":
                subject = f"Week {week_num} wrap-up - nice work, {name}!"
            else:
                subject = f"Week {week_num} check-in - did {chore} happen, {name}?"

        html = _load_template(
            template,
            {
                "NAME": name,
                "WEEK_NUM": str(week_num),
                "CHORE_ICON": CHORE_ICONS[chore],
                "CHORE_NAME": chore,
            },
        )

        if mode == "tuesday":
            text = (
                f"Hi {name},\n\n"
                f"Your chore for Week {week_num}: {chore}\n"
                f"Complete it any day before Monday.\n\n"
                f"Shared chore (everyone): Hallways - quick sweep, every week.\n\n"
                f"No strict deadline, just get it done before the week is out.\n"
                f"If you need to swap, let the house know.\n\n"
                f"Track it here: https://autumn-legacy.site\n\n"
                f"-- House Chores Tracker"
            )
        else:
            text = (
                f"Hi {name},\n\n"
                f"Week {week_num} check-in - did {chore} get done?\n\n"
                f"Your chore: {chore}\n"
                f"Shared chore (everyone): Hallways\n\n"
                f"Update your status: https://autumn-legacy.site\n\n"
                f"If something came up, just let the house know. No drama.\n"
                f"New rotation starts Tuesday.\n\n"
                f"-- House Chores Tracker"
            )

        recipients = [str(person_info["email"])]
        if "email2" in person_info:
            recipients.append(str(person_info["email2"]))
        _send_email(recipients, subject, html, text)

    if mode == "tuesday":
        seed_week(week_abs, schedule)
        print(f"  Database seeded for week {week_abs}.")


if __name__ == "__main__":
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if mode in ("tuesday", "monday"):
        send_reminders(mode)
    else:
        print("Usage: python -m lib.emailer [tuesday|monday]")
        sys.exit(1)
