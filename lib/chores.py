"""
lib/chores.py
=============
Shared rotation constants and scheduling logic.
Imported by both the Flask API (api/index.py) and the CLI emailer (chores_emailer.py).
"""

from datetime import date

# ── Rotation anchor ───────────────────────────────────────────────────────────

HOUSE_START_DATE: date = date(2026, 5, 4)  # First Monday of the rotation

# ── Housemates ────────────────────────────────────────────────────────────────

HOUSEMATES: dict[str, dict[str, str]] = {
    "Juan":     {"email": "jpc343@cornell.edu",       "color": "#3b82f6"},
    "Autumn":   {"email": "mingqizhong@gmail.com",    "color": "#f59e0b"},
    "Niranjan": {"email": "nvk7@cornell.edu",          "color": "#ef4444"},
    "Diwakar":  {"email": "diwakarraj149@gmail.com",  "color": "#8b5cf6"},
    "Pratyush": {"email": "ps2245@cornell.edu",       "color": "#06b6d4"},
}

# ── Chore metadata ────────────────────────────────────────────────────────────

CHORE_ICONS: dict[str, str] = {
    "Bathroom": "🛁",
    "Trash":    "🗑️",
    "Kitchen":  "🍳",
    "Hallways": "🧹",
}

CHORE_META: dict[str, dict[str, str]] = {
    "Bathroom": {"color": "#7c3aed", "bg": "#f5f3ff", "border": "#ddd6fe", "accent": "#EDE9FF"},
    "Trash":    {"color": "#ea580c", "bg": "#fff7ed", "border": "#fed7aa", "accent": "#FFF0E0"},
    "Kitchen":  {"color": "#d97706", "bg": "#fffbeb", "border": "#fde68a", "accent": "#FFFAE0"},
    "Hallways": {"color": "#16a34a", "bg": "#f0fdf4", "border": "#bbf7d0", "accent": "#E8F8EE"},
}

# ── Rotation pools ────────────────────────────────────────────────────────────
# Each index corresponds to one of the 4 rotation weeks (0-based).

BATHROOM_POOL:  list[str] = ["Autumn",  "Diwakar",  "Pratyush", "Niranjan"]
KITCHEN_POOL:   list[str] = ["Juan",    "Autumn",   "Diwakar",  "Niranjan"]
TRASH_PARTNERS: list[str] = ["Juan",    "Autumn",   "Diwakar",  "Pratyush"]
# Niranjan is always on Trash; TRASH_PARTNERS is his co-assigned partner.

# ── Core helpers ──────────────────────────────────────────────────────────────

def get_week_number() -> int:
    """
    Returns the current absolute week index (0-based) counting from
    HOUSE_START_DATE. Week 0 is the first week of the rotation.
    """
    today = date.today()
    delta = (today - HOUSE_START_DATE).days
    return max(0, delta // 7)


def get_rotation_week(week_abs: int) -> int:
    """Returns the 1-based rotation week number (1–4) for an absolute week."""
    return (week_abs % 4) + 1


def get_week_schedule(week_abs: int) -> dict[str, list[str]]:
    """
    Computes the chore schedule for a given absolute week.

    Returns a mapping of {person_name: [chore, ...]} where every
    housemate always receives "Hallways" plus any personally assigned chores.
    """
    idx: int = week_abs % 4
    schedule: dict[str, list[str]] = {name: ["Hallways"] for name in HOUSEMATES}

    schedule[BATHROOM_POOL[idx]].append("Bathroom")
    schedule[KITCHEN_POOL[idx]].append("Kitchen")

    # Niranjan is always paired on Trash with a rotating partner.
    schedule["Niranjan"].append("Trash")
    partner = TRASH_PARTNERS[idx]
    if partner != "Niranjan":
        schedule[partner].append("Trash")

    return schedule
