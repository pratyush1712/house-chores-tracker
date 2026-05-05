"""lib/db.py — Upstash Redis client for task statuses and person stats.

Key schema:
  task:{week_abs}:{person}:{chore}  → JSON { status, marked_at }
  stats:{person}                    → Hash { done_on_time, done_late, skipped, streak, last_week_abs }
  weeks_seen                        → ZSet { week_abs → score }

Requires UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN in env.
Falls back to safe no-op defaults when Redis is unavailable.
"""

import json
import os
from datetime import datetime, timezone
from typing import Literal, TypedDict

from upstash_redis import Redis

TaskStatus = Literal["pending", "done", "skipped"]


class PersonStats(TypedDict):
    done_on_time: int   # marked done before Sunday 18:00 EST
    done_late: int
    skipped: int
    streak: int         # consecutive weeks with at least one done task
    last_week_abs: int  # -1 means never recorded


_STATS_DEFAULTS: PersonStats = {
    "done_on_time": 0,
    "done_late": 0,
    "skipped": 0,
    "streak": 0,
    "last_week_abs": -1,
}

_redis: Redis | None = None


def _get_redis() -> Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    if not os.getenv("UPSTASH_REDIS_REST_URL") or not os.getenv("UPSTASH_REDIS_REST_TOKEN"):
        return None
    _redis = Redis.from_env()
    return _redis


def _task_key(week_abs: int, person: str, chore: str) -> str:
    return f"task:{week_abs}:{person}:{chore}"


def _stats_key(person: str) -> str:
    return f"stats:{person}"


def _is_on_time(week_abs: int, marked_at: datetime) -> bool:
    """Sunday 18:00 EST (22:00 UTC, fixed EDT offset) is the weekly deadline."""
    from datetime import timedelta
    from lib.chores import HOUSE_START_DATE

    week_sunday = HOUSE_START_DATE + timedelta(weeks=week_abs, days=6)
    deadline = datetime(week_sunday.year, week_sunday.month, week_sunday.day,
                        22, 0, 0, tzinfo=timezone.utc)
    return marked_at <= deadline


def get_task_status(week_abs: int, person: str, chore: str) -> TaskStatus:
    r = _get_redis()
    if r is None:
        return "pending"
    raw = r.get(_task_key(week_abs, person, chore))
    if raw is None:
        return "pending"
    try:
        status = json.loads(raw).get("status", "pending")
        if status in ("pending", "done", "skipped"):
            return status  # type: ignore[return-value]
    except (json.JSONDecodeError, TypeError):
        pass
    return "pending"


def set_task_status(week_abs: int, person: str, chore: str, status: TaskStatus) -> None:
    r = _get_redis()
    if r is None:
        return
    now = datetime.now(timezone.utc)
    r.set(_task_key(week_abs, person, chore),
          json.dumps({"status": status, "marked_at": now.isoformat()}))
    r.zadd("weeks_seen", {str(week_abs): week_abs})
    if status in ("done", "skipped"):
        _update_stats(r, person, week_abs, status, now)


def _update_stats(r: Redis, person: str, week_abs: int,
                  status: TaskStatus, marked_at: datetime) -> None:
    key = _stats_key(person)
    raw = r.hgetall(key)
    cur: PersonStats = {
        "done_on_time":  int(raw.get("done_on_time",  0)),
        "done_late":     int(raw.get("done_late",     0)),
        "skipped":       int(raw.get("skipped",       0)),
        "streak":        int(raw.get("streak",        0)),
        "last_week_abs": int(raw.get("last_week_abs", -1)),
    }
    new_week = cur["last_week_abs"] != week_abs
    if status == "done":
        if _is_on_time(week_abs, marked_at):
            cur["done_on_time"] += 1
        else:
            cur["done_late"] += 1
        if new_week:
            cur["streak"] += 1
    elif status == "skipped":
        cur["skipped"] += 1
        if new_week:
            cur["streak"] = 0
    cur["last_week_abs"] = week_abs
    r.hset(key, values={k: str(v) for k, v in cur.items()})


def get_person_stats(person: str) -> PersonStats:
    r = _get_redis()
    if r is None:
        return dict(_STATS_DEFAULTS)  # type: ignore[return-value]
    raw = r.hgetall(_stats_key(person))
    if not raw:
        return dict(_STATS_DEFAULTS)  # type: ignore[return-value]
    return {
        "done_on_time":  int(raw.get("done_on_time",  0)),
        "done_late":     int(raw.get("done_late",     0)),
        "skipped":       int(raw.get("skipped",       0)),
        "streak":        int(raw.get("streak",        0)),
        "last_week_abs": int(raw.get("last_week_abs", -1)),
    }


def get_all_stats(housemates: list[str]) -> dict[str, PersonStats]:
    return {person: get_person_stats(person) for person in housemates}


def get_week_statuses(week_abs: int,
                      schedule: dict[str, list[str]]) -> dict[str, dict[str, TaskStatus]]:
    return {
        person: {chore: get_task_status(week_abs, person, chore) for chore in chores}
        for person, chores in schedule.items()
    }


def seed_week(week_abs: int, schedule: dict[str, list[str]]) -> None:
    r = _get_redis()
    if r is None:
        return
    for person, chores in schedule.items():
        for chore in chores:
            key = _task_key(week_abs, person, chore)
            if r.get(key) is None:
                set_task_status(week_abs, person, chore, "pending")
