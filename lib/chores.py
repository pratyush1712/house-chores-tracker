"""lib/chores.py — rotation constants and scheduling logic."""

from datetime import date

HOUSE_START_DATE: date = date(2026, 5, 4)

HOUSEMATES: dict[str, dict[str, str]] = {
    "Juan":     {"email": "jpc343@cornell.edu",      "color": "#3b82f6"},
    "Autumn":   {"email": "mingqizhong@gmail.com",   "color": "#f59e0b"},
    "Niranjan": {"email": "nvk7@cornell.edu",         "color": "#ef4444"},
    "Diwakar":  {"email": "diwakarraj149@gmail.com", "color": "#8b5cf6"},
    "Pratyush": {"email": "ps2245@cornell.edu",      "color": "#06b6d4"},
}

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


def get_week_number() -> int:
    return max(0, (date.today() - HOUSE_START_DATE).days // 7)


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
    return (week_abs % len(POOLS["Bathroom"])) + 1
