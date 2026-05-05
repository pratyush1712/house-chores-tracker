# ruff: noqa: E402
"""
api/index.py
============
Flask application - served as a Vercel Python serverless function.

Vercel routes all traffic here via vercel.json. The module-level `app`
object is what Vercel's runtime invokes.

E402 (module-level import not at top of file) is suppressed file-wide because
sys.path must be patched and .env loaded before any local package imports can
succeed. This is an intentional Vercel serverless bootstrap pattern.

Routes:
  GET  /                           → Dashboard HTML
  GET  /api/meta                   → Static people, chore, rotation data
  GET  /api/schedule               → Current week schedule + task statuses
  GET  /api/schedule/<week_abs>    → Specific week schedule + statuses
  POST /api/mark                   → Update a task status
  GET  /api/stats                  → Lifetime completion stats for all housemates
  POST /api/send-reminders         → Trigger email send (monday | sunday | auto)
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# ── Bootstrap: patch sys.path before any local imports ────────────────────────
# When Vercel runs this file, __file__ is /var/task/api/index.py.
# The project root must be on sys.path so that `lib.*` is importable.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from flask import Flask, abort, jsonify, request, send_file
from flask.typing import ResponseReturnValue

from lib.chores import (
    CHORE_ICONS,
    CHORE_META,
    CHORE_TASKS,
    HOUSE_START_DATE,
    HOUSEMATES,
    POOLS,
    get_rotation_week,
    get_week_number,
    get_week_schedule,
)
from lib.db import get_all_stats, get_week_statuses, set_task_status
from lib.emailer import send_reminders

# ── App factory ───────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=None)

_DASHBOARD_HTML = os.path.abspath(
    os.path.join(_PROJECT_ROOT, "static", "dashboard.html")
)

# ── Routes ────────────────────────────────────────────────────────────────────


@app.route("/")
def dashboard() -> ResponseReturnValue:
    """Serves the static dashboard SPA."""
    return send_file(_DASHBOARD_HTML, mimetype="text/html")


@app.route("/api/meta")
def meta() -> ResponseReturnValue:
    """Returns static configuration data used by the dashboard on first load."""
    current_week_abs = get_week_number()
    current_week_num = get_rotation_week(current_week_abs)

    return jsonify(
        {
            "housemates": HOUSEMATES,
            "chore_icons": CHORE_ICONS,
            "chore_meta": CHORE_META,
            "chore_tasks": CHORE_TASKS,
            "pools": POOLS,
            "start_date": HOUSE_START_DATE.isoformat(),
            "current_week_abs": current_week_abs,
            "current_week_num": current_week_num,
        }
    )


@app.route("/api/schedule")
def current_schedule() -> ResponseReturnValue:
    """Returns the current week's schedule and task statuses."""
    return _schedule_response(get_week_number())


@app.route("/api/schedule/<int:week_abs>")
def week_schedule(week_abs: int) -> ResponseReturnValue:
    """Returns a specific week's schedule and statuses by absolute week index."""
    current = get_week_number()
    if week_abs < 0 or week_abs > current + 52:
        abort(400, description="week_abs out of valid range")
    return _schedule_response(week_abs)


def _schedule_response(week_abs: int) -> ResponseReturnValue:
    """Shared helper that builds a schedule + status response."""
    try:
        schedule = get_week_schedule(week_abs)
        statuses = get_week_statuses(week_abs, schedule)
    except Exception as exc:
        return jsonify({"error": f"Database error: {exc}"}), 503
    return jsonify(
        {
            "week_abs": week_abs,
            "week_num": get_rotation_week(week_abs),
            "is_current": week_abs == get_week_number(),
            "schedule": schedule,
            "statuses": statuses,
        }
    )


@app.route("/api/mark", methods=["POST"])
def mark_task() -> ResponseReturnValue:
    """
    Updates the status of a single task.

    Expected JSON body:
      {
        "week_abs": int,
        "person":   str,
        "chore":    str,
        "status":   "done" | "pending" | "skipped"
      }
    """
    body: dict[str, object] | None = request.get_json(force=True, silent=True)
    if not body:
        abort(400, description="JSON body is required")

    week_abs = body.get("week_abs")
    person = body.get("person")
    chore = body.get("chore")
    status = body.get("status")

    # Validate all required fields are present and typed correctly.
    if not isinstance(week_abs, int):
        abort(400, description="week_abs must be an integer")
    current_week = get_week_number()
    if week_abs < max(0, current_week - 1) or week_abs > current_week + 1:
        abort(400, description="week_abs out of allowed range (current week ± 1)")
    if not isinstance(person, str) or person not in HOUSEMATES:
        abort(400, description=f"Unknown person: {person!r}")
    if not isinstance(chore, str) or chore not in CHORE_META:
        abort(400, description=f"Unknown chore: {chore!r}")
    if status not in ("done", "pending", "skipped"):
        abort(400, description="status must be 'done', 'pending', or 'skipped'")

    try:
        set_task_status(week_abs, person, chore, status)  # type: ignore[arg-type]
    except Exception as exc:
        return jsonify({"error": f"Database error: {exc}"}), 503

    return jsonify(
        {
            "ok": True,
            "week_abs": week_abs,
            "person": person,
            "chore": chore,
            "status": status,
        }
    )


@app.route("/api/stats")
def stats() -> ResponseReturnValue:
    """
    Returns lifetime completion stats for every housemate.

    Response shape:
      {
        "Juan":     { done_on_time, done_late, skipped, streak, last_week_abs },
        "Autumn":   { ... },
        ...
      }
    """
    all_stats = get_all_stats(list(HOUSEMATES.keys()))
    return jsonify(all_stats)


@app.route("/api/send-reminders", methods=["POST"])
def send_reminders_route() -> ResponseReturnValue:
    """
    Triggers an email batch for the current week.

    Optional JSON body:
      { "mode": "tuesday" | "monday" | "auto" }

    "auto" (default) inspects the current day in EST:
      - Tuesday  → sends tuesday assignment emails
      - Monday   → sends monday check-in emails
      - Any other day → sends tuesday assignment emails as a manual override

    Returns:
      { "ok": true, "mode": "tuesday" | "monday", "detail": "..." }
    """

    body: dict[str, object] = request.get_json(force=True, silent=True) or {}
    requested_mode: object = body.get("mode", "auto")

    if not isinstance(requested_mode, str) or requested_mode not in (
        "tuesday",
        "monday",
        "auto",
    ):
        abort(400, description="mode must be 'tuesday', 'monday', or 'auto'")

    if requested_mode == "auto":
        now = datetime.now(ZoneInfo("America/New_York"))
        weekday = now.weekday()  # 0=Mon 1=Tue … 6=Sun
        resolved_mode: str = "monday" if weekday == 0 else "tuesday"
    else:
        resolved_mode = requested_mode

    try:
        send_reminders(resolved_mode)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "mode": resolved_mode,
            "detail": f"{'Tuesday assignment' if resolved_mode == 'tuesday' else 'Monday check-in'} emails sent.",
        }
    )


# ── Error handlers ────────────────────────────────────────────────────────────


@app.errorhandler(400)
def bad_request(err: object) -> ResponseReturnValue:
    return jsonify({"error": str(err)}), 400


@app.errorhandler(404)
def not_found(err: object) -> ResponseReturnValue:
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(err: object) -> ResponseReturnValue:
    return jsonify({"error": "Internal server error"}), 500


# ── Local dev entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
