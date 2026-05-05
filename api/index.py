"""
api/index.py
============
Flask application — served as a Vercel Python serverless function.

Vercel routes all traffic here via vercel.json. The module-level `app`
object is what Vercel's runtime invokes.

Routes:
  GET  /                           → Dashboard HTML
  GET  /api/meta                   → Static people, chore, rotation data
  GET  /api/schedule               → Current week schedule + task statuses
  GET  /api/schedule/<week_abs>    → Specific week schedule + statuses
  POST /api/mark                   → Update a task status
"""

import os
import sys

# Ensure the project root is importable when running as a Vercel serverless
# function, where __file__ resolves to /var/task/api/index.py.
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
    HOUSE_START_DATE,
    HOUSEMATES,
    get_rotation_week,
    get_week_number,
    get_week_schedule,
)
from lib.db import TaskStatus, get_week_statuses, set_task_status

# ── App factory ───────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=None)

_DASHBOARD_HTML = os.path.abspath(
    os.path.join(_PROJECT_ROOT, "chores_dashboard.html")
)

# ── Routes ────────────────────────────────────────────────────────────────────


@app.route("/")
def dashboard() -> ResponseReturnValue:
    """Serves the static dashboard SPA."""
    return send_file(_DASHBOARD_HTML, mimetype="text/html")


@app.route("/api/meta")
def meta() -> ResponseReturnValue:
    """
    Returns static configuration data used by the dashboard on first load:
    housemates, chore definitions, the 4-week rotation schedule, and the
    current week's position in the rotation.
    """
    current_week_abs = get_week_number()
    current_week_num = get_rotation_week(current_week_abs)

    rotation: list[dict[str, object]] = []
    for i in range(4):
        rotation.append({
            "week_num": i + 1,
            "schedule": get_week_schedule(i),
        })

    return jsonify({
        "housemates": HOUSEMATES,
        "chore_icons": CHORE_ICONS,
        "chore_meta": CHORE_META,
        "rotation": rotation,
        "start_date": HOUSE_START_DATE.isoformat(),
        "current_week_abs": current_week_abs,
        "current_week_num": current_week_num,
    })


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
    schedule = get_week_schedule(week_abs)
    statuses = get_week_statuses(week_abs, schedule)
    return jsonify({
        "week_abs": week_abs,
        "week_num": get_rotation_week(week_abs),
        "is_current": week_abs == get_week_number(),
        "schedule": schedule,
        "statuses": statuses,
    })


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
    person   = body.get("person")
    chore    = body.get("chore")
    status   = body.get("status")

    # Validate all required fields are present and typed correctly.
    if not isinstance(week_abs, int):
        abort(400, description="week_abs must be an integer")
    if not isinstance(person, str) or person not in HOUSEMATES:
        abort(400, description=f"Unknown person: {person!r}")
    if not isinstance(chore, str) or chore not in CHORE_META:
        abort(400, description=f"Unknown chore: {chore!r}")
    if status not in ("done", "pending", "skipped"):
        abort(400, description="status must be 'done', 'pending', or 'skipped'")

    set_task_status(week_abs, person, chore, status)  # type: ignore[arg-type]

    return jsonify({
        "ok": True,
        "week_abs": week_abs,
        "person": person,
        "chore": chore,
        "status": status,
    })


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(400)
def bad_request(err: object) -> ResponseReturnValue:
    return jsonify({"error": str(err)}), 400


@app.errorhandler(404)
def not_found(err: object) -> ResponseReturnValue:
    return jsonify({"error": "Not found"}), 404


# ── Local dev entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
