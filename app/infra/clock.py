from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


@dataclass(frozen=True)
class SessionWindow:
    start_hour: int  # inclusive local hour (0-23)
    end_hour: int  # exclusive local hour (0-23); may be < start_hour for overnight windows
    tz: ZoneInfo = JAKARTA_TZ


def now_local(tz: Optional[ZoneInfo] = JAKARTA_TZ) -> datetime:
    return datetime.now(tz)


def is_weekday(dt: datetime) -> bool:
    # Monday=0 ... Sunday=6
    return dt.weekday() < 5


def _is_overnight(window: SessionWindow) -> bool:
    # Overnight if the session end is on the next day
    return window.end_hour <= window.start_hour


def in_session(dt: datetime, window: SessionWindow) -> bool:
    """
    True if 'dt' is within the active session window.
    For overnight windows (e.g., 07:00 -> 03:00 next day), hours after midnight
    (00:00..end_hour-1) belong to the previous day's session.
    """
    h = dt.hour
    if not _is_overnight(window):
        # Same-day session: (start, end)
        return is_weekday(dt) and (window.start_hour <= h < window.end_hour)

    # Overnight session
    # Part A (evening): from today's start_hour to 23:59
    if is_weekday(dt) and h >= window.start_hour:
        return True
    # Part B (early morning): from 00:00 to end_hour-1, but belongs to previous weekday
    prev_day = dt - timedelta(days=1)
    return is_weekday(prev_day) and h < window.end_hour


def session_start_for(dt: datetime, window: SessionWindow) -> Optional[datetime]:
    """
    If 'dt' is inside a session, return the local datetime representing the
    start of that session; otherwise return None.
    """
    if not in_session(dt, window):
        return None

    if not _is_overnight(window):
        # Same-day start at today's start_hour
        return dt.replace(hour=window.start_hour, minute=0, second=0, microsecond=0)

    # Overnight: two cases
    h = dt.hour
    if is_weekday(dt) and h >= window.start_hour:
        # Evening part belongs to today; start is today at start_hour
        return dt.replace(hour=window.start_hour, minute=0, second=0, microsecond=0)

    # Early morning part belongs to previous weekday; start is yesterday at start_hour
    prev_day = dt - timedelta(days=1)
    # Find previous weekday (skip weekend if needed)
    while not is_weekday(prev_day):
        prev_day -= timedelta(days=1)

    start = prev_day.replace(hour=window.start_hour, minute=0, second=0, microsecond=0)
    return start


def _next_weekday_start(after: datetime, window: SessionWindow) -> datetime:
    """
    Return the next session start (local time) strictly after the 'after' arg value,
    occurring on the next valid weekday at start_hour.
    """
    day = after
    # Move to next day first to ensure strictly after
    day = (day + timedelta(days=1)).replace(hour=window.start_hour, minute=0, second=0, microsecond=0)
    while not is_weekday(day):
        day = day + timedelta(days=1)
    return day


def next_session_start(dt: datetime, window: SessionWindow) -> datetime:
    """
    Return the next local datetime at window.start_hour (Mon to Fri), given 'dt'.
        - If we're before today's start and today is weekday => today's start.
        - If in session => start of the *next* session (skip weekends).
        - If between end and next start => today's start if weekday, else next weekday.
        - Correctly handles overnight windows (e.g., 07:00 -> 03:00 next day).
    """
    h = dt.hour

    # If currently in a session, schedule the next session start after this one.
    start_of_current = session_start_for(dt, window)
    if start_of_current is not None:
        return _next_weekday_start(start_of_current, window)

    if not _is_overnight(window):
        # Same-day window
        today_start = dt.replace(hour=window.start_hour, minute=0, second=0, microsecond=0)
        if is_weekday(dt) and dt < today_start:
            return today_start
        return _next_weekday_start(dt, window)

    # Overnight window (e.g., 07 -> 03)
    # If we're before today's start and today is a weekday, next start is today 07:00.
    today_start = dt.replace(hour=window.start_hour, minute=0, second=0, microsecond=0)
    if is_weekday(dt) and dt < today_start:
        return today_start

    # If we're in the early-morning gap (>= end_hour and < start_hour) on a weekday,
    # next start is today at start_hour.
    if is_weekday(dt) and (window.end_hour <= h < window.start_hour):
        return today_start

    # Otherwise, jump to next weekday's start.
    return _next_weekday_start(dt, window)


def sleep_until(target: datetime) -> None:
    """
    Sleep until the given local target time; safe if target is in the past (no-op).
    Falls back to JAKARTA_TZ if target has no ZoneInfo (e.g., fixed UTC offset).
    """
    tz = target.tzinfo if isinstance(target.tzinfo, ZoneInfo) else JAKARTA_TZ
    delay = (target - now_local(tz)).total_seconds()
    if delay > 0:
        time.sleep(delay)


@warnings.deprecated(
    "Validating timezone using `isinstance()` should be preferred, for example: `tz = target.tzinfo if isinstance(target.tzinfo, ZoneInfo) else JAKARTA_TZ`.",
    category=DeprecationWarning,
)
def get_zoneinfo(dt: datetime) -> Optional[ZoneInfo]:
    """
    Safely extracts the ZoneInfo object from a datetime object's tzinfo,
    converting from legacy tzinfo objects if necessary.
    """
    if dt.tzinfo is None:
        return None

    # Check if it's already a modern ZoneInfo instance
    if isinstance(dt.tzinfo, ZoneInfo):
        return dt.tzinfo

    # If it's a legacy tzinfo (like pytz), get its canonical name string.
    try:
        # Most legacy tzinfo objects have a .key or .zone attribute
        tz_name = getattr(dt.tzinfo, "key", getattr(dt.tzinfo, "zone", None))

        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        # Fallback for complex/non-standard tzinfo objects
        pass

    # If all attempts fail, or it's a fixed offset like timezone.utc,
    # we can't reliably convert it to a named ZoneInfo object.
    return None


def humanize_timedelta(delta: timedelta) -> str:
    """
    Converts a datetime.timedelta object into a human-readable string format,
    including hours, minutes, seconds, and milliseconds.

    Args:
        delta: The timedelta object to convert.

    Returns:
        A formatted string (e.g., "1h 23m 58s 987ms").
    """

    # Get the total seconds as an integer (milliseconds/microseconds excluded)
    total_seconds = int(delta.total_seconds())

    # Calculate hours, minutes, and remaining seconds
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    formatted_time = f"{hours}hr {minutes}min {seconds}sec"
    return formatted_time
