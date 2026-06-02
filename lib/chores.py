"""lib/chores.py - rotation constants and scheduling logic."""

from datetime import date

HOUSE_START_DATE: date = date(2026, 5, 4)

HOUSEMATES: dict[str, dict[str, str]] = {
    "Juan": {"email": "jpc343@cornell.edu", "color": "#3b82f6"},
    "Autumn": {
        "email": "mingqizhong@gmail.com",
        "email2": "mz668@cornell.edu",
        "color": "#f59e0b",
    },
    "Niranjan": {"email": "nvk7@cornell.edu", "color": "#ef4444", "trash_day": "Mon"},
    "Diwakar": {
        "email": "diwakarraj149@gmail.com",
        "email2": "ds2493@cornell.edu",
        "color": "#8b5cf6",
    },
    "Pratyush": {"email": "ps2245@cornell.edu", "color": "#06b6d4"},
}

CHORE_ICONS: dict[str, str] = {
    "Bathroom": "🛁",
    "Trash": "🗑️",
    "Kitchen": "🍳",
    "Hallways": "🧹",
}

CHORE_TASKS: dict[str, list[str]] = {
    "Bathroom": [
        "Scrub toilet",
        "Wipe sink & mirror",
        "Scrub shower",
        "Mop floor",
        "Empty bin",
    ],
    "Kitchen": [
        "Wipe stove & countertops",
        "Sweep floor",
    ],
    "Trash": [
        "Empty kitchen trash (Thu)",
        "Put out bins Mon morning - Niranjan",
        "Attach trash tags",
        "Return bins after pickup",
        "Clean up any dropped trash",
    ],
    "Hallways": [
        "Vacuum both floors",
        "Mop if needed",
    ],
}

CHORE_META: dict[str, dict[str, str | bool]] = {
    "Bathroom": {
        "color": "#7c3aed",
        "bg": "#f5f3ff",
        "border": "#ddd6fe",
        "accent": "#EDE9FF",
        "text_color": "#5B21B6",
        "icon": "bath",
        "shared": False,
    },
    "Trash": {
        "color": "#ea580c",
        "bg": "#fff7ed",
        "border": "#fed7aa",
        "accent": "#FFF0E0",
        "text_color": "#C2410C",
        "icon": "trash",
        "shared": False,
    },
    "Kitchen": {
        "color": "#d97706",
        "bg": "#fffbeb",
        "border": "#fde68a",
        "accent": "#FFFAE0",
        "text_color": "#B45309",
        "icon": "kitchen",
        "shared": False,
    },
    "Hallways": {
        "color": "#16a34a",
        "bg": "#f0fdf4",
        "border": "#bbf7d0",
        "accent": "#E8F8EE",
        "text_color": "#15803D",
        "icon": "hallway",
        "shared": True,
    },
}

# Number of weeks before the displayed rotation week number resets to 1.
# Shown on the dashboard and in email subjects as "Week N".
ROTATION_CYCLE_LENGTH: int = 4

# Each chore rotates through its own pool independently (different lengths are fine).
# Inner list = all assignees for that slot. Niranjan is fixed on Trash every week.
POOLS: dict[str, list[list[str]]] = {
    "Bathroom": [
        ["Pratyush"],
        ["Niranjan"],
        ["Diwakar"],
        ["Autumn"],
    ],
    "Kitchen": [
        ["Diwakar"],
        ["Autumn"],
        ["Niranjan"],
        ["Juan"],
    ],
    "Trash": [
        ["Niranjan", "Diwakar"],
        ["Niranjan", "Autumn"],
        ["Niranjan", "Juan"],
        ["Niranjan", "Pratyush"],
    ],
    "Hallways": [
        ["Pratyush"],
        ["Niranjan"],
        ["Diwakar"],
        ["Autumn"],
        ["Juan"],
    ],
}


def get_week_number(today: date | None = None) -> int:
    current = today or date.today()
    days_since_anchor = (current - HOUSE_START_DATE).days
    return max(0, (days_since_anchor - 1) // 7)


def get_assignees(chore: str, week_abs: int) -> list[str]:
    pool = POOLS[chore]
    return pool[week_abs % len(pool)]


def get_week_schedule(week_abs: int) -> dict[str, list[str]]:
    schedule: dict[str, list[str]] = {name: [] for name in HOUSEMATES}
    for chore, pool in POOLS.items():
        for person in pool[week_abs % len(pool)]:
            schedule[person].append(chore)
    return schedule


def get_rotation_week(week_abs: int) -> int:
    return (week_abs % ROTATION_CYCLE_LENGTH) + 1
