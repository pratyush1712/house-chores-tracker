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
import re
import smtplib
import sys
from typing import TypedDict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from dotenv import load_dotenv

load_dotenv()

from lib.chores import (
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


class RenderedReminderEmail(TypedDict):
    name: str
    recipients: list[str]
    subject: str
    text: str
    html: str



def _assignment_label(chores: list[str]) -> str:
    if len(chores) == 1:
        return chores[0]
    return ", ".join(chores[:-1]) + f" and {chores[-1]}"


def _count_label(count: int) -> str:
    noun = "chore" if count == 1 else "chores"
    return f"{count} {noun}"


def _assignment_count_label(chores: list[str]) -> str:
    return _count_label(len(chores))


def _status_mark(status_label: str) -> str:
    if status_label == "Done":
        return "●"
    if status_label == "Skipped":
        return "-"
    if status_label == "Needs update":
        return "○"
    return "■"


def _assignment_rows(chores: list[str], mode: str, week_abs: int, name: str) -> str:
    rows: list[str] = []
    for index, chore in enumerate(chores, start=1):
        status = (
            get_task_status(week_abs, name, chore)
            if mode == "monday"
            else "pending"
        )
        if mode == "tuesday":
            status_label = "Assigned"
        elif status == "done":
            status_label = "Done"
        elif status == "skipped":
            status_label = "Skipped"
        else:
            status_label = "Needs update"
        status_mark = _status_mark(status_label)
        rows.append(
            "\n".join(
                [
                    '<tr>',
                    '  <td style="padding: 0 0 16px;">',
                    '    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #ffffff; border: 4px solid #2A2A30; border-radius: 0;">',
                    '      <tr>',
                    f'        <td width="72" valign="top" style="padding: 16px 12px; background: #E8DED0; border-right: 2px solid #2A2A30; font-family: Menlo, Monaco, Consolas, monospace; font-size: 12px; line-height: 16px; letter-spacing: 1.44px; color: #242429; font-weight: 900; text-transform: uppercase;">TASK<br />{index:02d}</td>',
                    '        <td valign="top" style="padding: 16px 18px;">',
                    f'          <div style="font-family: Arial, Helvetica, sans-serif; font-size: 24px; line-height: 25px; letter-spacing: -0.48px; color: #242429; font-weight: 900; text-transform: uppercase;">{chore}</div>',
                    f'          <div style="font-family: Menlo, Monaco, Consolas, monospace; font-size: 12px; line-height: 16px; letter-spacing: 0.96px; color: #5C5C66; font-weight: 800; text-transform: uppercase; margin-top: 10px;">{status_mark} {status_label} / Due Monday night</div>',
                    '        </td>',
                    '      </tr>',
                    '    </table>',
                    '  </td>',
                    '</tr>',
                ]
            )
        )
    return "\n".join(rows)


def _plain_chore_lines(chores: list[str]) -> str:
    return "\n".join(f"- {chore}" for chore in chores)


def _pending_chores(week_abs: int, name: str, chores: list[str]) -> list[str]:
    return [
        chore
        for chore in chores
        if get_task_status(week_abs, name, chore) == "pending"
    ]


def _monday_status_summary(week_abs: int, name: str, chores: list[str]) -> str:
    pending = _pending_chores(week_abs, name, chores)
    if not pending:
        return "Everything assigned to you has been updated. Nice work."
    return f"Still needs an update: {_assignment_label(pending)}."


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


def _validate_mode(mode: str) -> None:
    if mode not in ("tuesday", "monday"):
        raise ValueError(f"mode must be 'tuesday' or 'monday', got {mode!r}")


def _safe_preview_filename(mode: str, week_num: int, name: str) -> str:
    safe_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "person"
    return f"week-{week_num}-{mode}-{safe_name}.html"


def render_reminder_emails(mode: str) -> list[dict[str, object]]:
    """Render reminder emails without sending them."""
    _validate_mode(mode)

    week_abs = get_week_number()
    week_num = get_rotation_week(week_abs)
    schedule = get_week_schedule(week_abs)
    template = f"email_{mode}.html"
    rendered: list[dict[str, object]] = []

    for name, chores in schedule.items():
        if not chores:
            continue

        person_info = HOUSEMATES[name]
        chore_summary = _assignment_label(chores)
        assignment_count = _assignment_count_label(chores)

        if mode == "tuesday":
            subject = f"Chores - Week {week_num}: {chore_summary}, {name}"
            status_summary = "New assignments for this Tuesday-to-Monday cycle."
        else:
            status_summary = _monday_status_summary(week_abs, name, chores)
            pending_count = len(_pending_chores(week_abs, name, chores))
            if pending_count == 0:
                subject = f"Week {week_num} wrap-up - nice work, {name}!"
            else:
                subject = (
                    f"Week {week_num} check-in - "
                    f"{_count_label(pending_count)} to update, {name}"
                )

        html = _load_template(
            template,
            {
                "NAME": name,
                "WEEK_NUM": str(week_num),
                "ASSIGNMENT_COUNT": assignment_count,
                "CHORE_SUMMARY": chore_summary,
                "STATUS_SUMMARY": status_summary,
                "PRIMARY_CHORE_ROWS": _assignment_rows(
                    chores, mode, week_abs, name
                ),
            },
        )

        if mode == "tuesday":
            text = (
                f"Hi {name},\n\n"
                f"Your Week {week_num} chores:\n"
                f"{_plain_chore_lines(chores)}\n\n"
                f"Finish your assigned chores before Monday night. "
                f"If you need to swap, let the house know.\n\n"
                f"Track it here: https://autumn-legacy.site\n\n"
                f"-- House Chores Tracker"
            )
        else:
            text = (
                f"Hi {name},\n\n"
                f"Week {week_num} check-in.\n"
                f"{status_summary}\n\n"
                f"Your assigned chores this week:\n"
                f"{_plain_chore_lines(chores)}\n\n"
                f"Update your status: https://autumn-legacy.site\n\n"
                f"If something came up, let the house know. New rotation starts Tuesday.\n\n"
                f"-- House Chores Tracker"
            )

        recipients = [str(person_info["email"])]
        if "email2" in person_info:
            recipients.append(str(person_info["email2"]))

        rendered.append(
            {
                "name": name,
                "recipients": recipients,
                "subject": subject,
                "html": html,
                "text": text,
                "week_abs": week_abs,
                "week_num": week_num,
                "mode": mode,
                "chores": list(chores),
            }
        )

    return rendered


def preview_reminders(mode: str, output_dir: str = ".email-previews") -> list[dict[str, object]]:
    """Render emails, write HTML previews, and print a no-send summary."""
    rendered = render_reminder_emails(mode)
    os.makedirs(output_dir, exist_ok=True)

    if not rendered:
        print(f"No {mode} reminder emails to preview.")
        return rendered

    week_num = int(rendered[0]["week_num"])
    print(f"\nPreviewing {mode} reminders - Week {week_num} (no email sent).")

    for email in rendered:
        name = str(email["name"])
        path = os.path.join(output_dir, _safe_preview_filename(mode, week_num, name))
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(email["html"]))

        recipients = ", ".join(str(item) for item in email["recipients"])
        print("\n" + "=" * 72)
        print(f"To: {recipients}")
        print(f"Subject: {email['subject']}")
        print(f"HTML preview: {path}")
        print("\nPlain text body:\n")
        print(email["text"])

    print("\nNo email was sent. Open the HTML preview files to inspect layout.")
    return rendered


def send_reminders(mode: str) -> None:
    """
    Send chore reminder emails to all housemates.

    mode="tuesday" - kick-off email (email_tuesday.html); also seeds the DB.
    mode="monday"  - check-in email (email_monday.html); subject personalised
                     by current completion status.
    """
    _validate_mode(mode)

    rendered = render_reminder_emails(mode)
    week_abs = int(rendered[0]["week_abs"]) if rendered else get_week_number()
    week_num = get_rotation_week(week_abs)
    schedule = get_week_schedule(week_abs)

    print(f"\nSending {mode} reminders - Week {week_num} (abs {week_abs})...")

    for name, chores in schedule.items():
        if not chores:
            print(f"  Skipping {name} - no chore assigned this week.")

    for email in rendered:
        recipients = [str(item) for item in email["recipients"]]
        _send_email(
            recipients,
            str(email["subject"]),
            str(email["html"]),
            str(email["text"]),
        )

    if mode == "tuesday":
        seed_week(week_abs, schedule)
        print(f"  Database seeded for week {week_abs}.")


if __name__ == "__main__":
    args = [arg.lower() for arg in sys.argv[1:]]
    if len(args) >= 2 and args[0] == "preview" and args[1] in ("tuesday", "monday"):
        preview_reminders(
            args[1], sys.argv[3] if len(sys.argv) > 3 else ".email-previews"
        )
    elif len(args) == 1 and args[0] in ("tuesday", "monday"):
        send_reminders(args[0])
    else:
        print("Usage: python -m lib.emailer [tuesday|monday]")
        print("       python -m lib.emailer preview [tuesday|monday] [output_dir]")
        sys.exit(1)
