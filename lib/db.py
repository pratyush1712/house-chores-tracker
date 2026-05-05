"""
lib/db.py
=========
Upstash Redis client for persisting chore task statuses.

Redis.from_env() reads two specific variable names:
  UPSTASH_REDIS_REST_URL    — REST endpoint
  UPSTASH_REDIS_REST_TOKEN  — read-write token

Vercel KV (also Upstash under the hood) injects differently-named variables:
  KV_REST_API_URL, KV_REST_API_TOKEN, etc.

The bridge: in Vercel's project settings, add two extra environment variables
that copy the KV values into the names upstash-redis expects:
  UPSTASH_REDIS_REST_URL   = ${KV_REST_API_URL}
  UPSTASH_REDIS_REST_TOKEN = ${KV_REST_API_TOKEN}

Locally, set those two names in .env (see .env.example).
If either is absent, all reads return "pending" and writes are silently skipped.
"""

import json
import os
from datetime import datetime, timezone
from typing import Literal

from upstash_redis import Redis

# ── Type aliases ──────────────────────────────────────────────────────────────

TaskStatus = Literal["pending", "done", "skipped"]

# ── Module-level singleton ────────────────────────────────────────────────────
# Reused across hot invocations on Vercel; created lazily on first call.

_redis: Redis | None = None


def _get_redis() -> Redis | None:
    """
    Returns a Redis client via Redis.from_env(), or None if the required
    UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN vars are not set.
    """
    global _redis
    if _redis is not None:
        return _redis
    if not os.getenv("UPSTASH_REDIS_REST_URL") or not os.getenv("UPSTASH_REDIS_REST_TOKEN"):
        return None
    _redis = Redis.from_env()
    return _redis


# ── Key helpers ───────────────────────────────────────────────────────────────

def _task_key(week_abs: int, person: str, chore: str) -> str:
    """Canonical Redis key for a single task."""
    return f"task:{week_abs}:{person}:{chore}"


# ── Public API ────────────────────────────────────────────────────────────────

def get_task_status(week_abs: int, person: str, chore: str) -> TaskStatus:
    """
    Returns the persisted status of a task.
    Defaults to "pending" when no record exists or Redis is unavailable.
    """
    r = _get_redis()
    if r is None:
        return "pending"
    raw = r.get(_task_key(week_abs, person, chore))
    if raw is None:
        return "pending"
    try:
        data: dict[str, str] = json.loads(raw)
        status = data.get("status", "pending")
        if status in ("pending", "done", "skipped"):
            return status  # type: ignore[return-value]
        return "pending"
    except (json.JSONDecodeError, TypeError):
        return "pending"


def set_task_status(
    week_abs: int,
    person: str,
    chore: str,
    status: TaskStatus,
) -> None:
    """
    Persists a task status.
    Also registers the week in the 'weeks_seen' sorted set for history queries.
    Silently no-ops when Redis is unavailable.
    """
    r = _get_redis()
    if r is None:
        return
    payload = json.dumps({
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    r.set(_task_key(week_abs, person, chore), payload)
    # Use a sorted set with the week number as score for cheap range queries.
    r.zadd("weeks_seen", {str(week_abs): week_abs})


def get_week_statuses(
    week_abs: int,
    schedule: dict[str, list[str]],
) -> dict[str, dict[str, TaskStatus]]:
    """
    Returns {person: {chore: status}} for all tasks in a given week.

    Keys are derived directly from the schedule so no Redis SCAN is needed.
    Tasks not yet recorded default to "pending".
    """
    statuses: dict[str, dict[str, TaskStatus]] = {}
    for person, chores in schedule.items():
        statuses[person] = {
            chore: get_task_status(week_abs, person, chore)
            for chore in chores
        }
    return statuses


def seed_week(week_abs: int, schedule: dict[str, list[str]]) -> None:
    """
    Pre-populates "pending" records for every task in a week, skipping
    tasks that already have a record. Called when Monday emails are sent
    so the dashboard shows all tasks immediately.
    """
    r = _get_redis()
    if r is None:
        return
    for person, chores in schedule.items():
        for chore in chores:
            key = _task_key(week_abs, person, chore)
            if r.get(key) is None:
                set_task_status(week_abs, person, chore, "pending")
