from collections import namedtuple
from datetime import datetime, timedelta

import mt5_wrapper as mt5

Timeframe = namedtuple("Timeframe", ["min", "sec", "human"])

# This map contains all standard MT5 timeframes. Refer to app/adapters/mt5_client.py
# to check the list of supported timeframe in this project,
_TIMEFRAME_MAP = {
    # MINUTE timeframes
    mt5.TIMEFRAME_M1: Timeframe(min=1, sec=60, human="1-minute"),
    mt5.TIMEFRAME_M2: Timeframe(min=2, sec=120, human="2-minute"),
    mt5.TIMEFRAME_M3: Timeframe(min=3, sec=180, human="3-minute"),
    mt5.TIMEFRAME_M4: Timeframe(min=4, sec=240, human="4-minute"),
    mt5.TIMEFRAME_M5: Timeframe(min=5, sec=300, human="5-minute"),
    mt5.TIMEFRAME_M6: Timeframe(min=6, sec=360, human="6-minute"),
    mt5.TIMEFRAME_M10: Timeframe(min=10, sec=600, human="10-minute"),
    mt5.TIMEFRAME_M12: Timeframe(min=12, sec=720, human="12-minute"),
    mt5.TIMEFRAME_M15: Timeframe(min=15, sec=900, human="15-minute"),
    mt5.TIMEFRAME_M20: Timeframe(min=20, sec=1200, human="20-minute"),
    mt5.TIMEFRAME_M30: Timeframe(min=30, sec=1800, human="30-minute"),
    # HOURLY timeframes
    mt5.TIMEFRAME_H1: Timeframe(min=60, sec=3600, human="1-hour"),
    mt5.TIMEFRAME_H2: Timeframe(min=120, sec=7200, human="2-hour"),
    mt5.TIMEFRAME_H3: Timeframe(min=180, sec=10800, human="3-hour"),
    mt5.TIMEFRAME_H4: Timeframe(min=240, sec=14400, human="4-hour"),
    mt5.TIMEFRAME_H6: Timeframe(min=360, sec=21600, human="6-hour"),
    mt5.TIMEFRAME_H8: Timeframe(min=480, sec=28800, human="8-hour"),
    mt5.TIMEFRAME_H12: Timeframe(min=720, sec=43200, human="12-hour"),
    # DAILY timeframe (with fixed minutes and seconds)
    mt5.TIMEFRAME_D1: Timeframe(min=1440, sec=86400, human="1-day"),
    # WEEKLY and MONTHLY timeframes (symbolic, not fixed counts)
    # Should not be used for minute/second arithmetic!
    mt5.TIMEFRAME_W1: Timeframe(min=None, sec=None, human="1-week"),
    mt5.TIMEFRAME_MN1: Timeframe(min=None, sec=None, human="1-month"),
}


def humanize_mt5_timeframe(timeframe: int) -> str:
    """
    Converts an MT5 timeframe constant (e.g., mt5.TIMEFRAME_H1)
    into a human-readable, hyphenated string (e.g., "1-hour").

    Args:
        timeframe: The MT5 timeframe constant in int.

    Returns:
        A formatted string (e.g., "4-hour") or a fallback
        string if the timeframe is not recognized.
    """

    # Use .get() for a safe lookup. It returns the value for the key,
    # or the default value if the key is not found.
    timeframe_tuple = _TIMEFRAME_MAP.get(timeframe)
    if not timeframe_tuple:
        return "unknown-timeframe"
    return timeframe_tuple.human


def timeframe_to_seconds(timeframe: int) -> int:
    if timeframe <= 0:
        raise ValueError("Timeframe must be greater than 0")

    timeframe_tuple = _TIMEFRAME_MAP.get(timeframe)
    if not timeframe_tuple:
        raise ValueError("Unknown timeframe")

    return timeframe_tuple.sec


def next_aligned_close(datetime: datetime, timeframe: int) -> datetime:
    """
    Given a local datetime and an MT5 timeframe constant (e.g., TIMEFRAME_M5),
    return the next candle-close boundary.
    """
    if timeframe <= 0:
        raise ValueError("Timeframe must be greater than 0")

    timeframe_tuple = _TIMEFRAME_MAP.get(timeframe)
    if not timeframe_tuple:
        raise ValueError("Unknown timeframe")

    timeframe_sec = timeframe_tuple.sec
    day_start = datetime.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((datetime - day_start).total_seconds())
    remainder = elapsed % timeframe_sec
    delta = timeframe_sec - remainder if remainder != 0 else timeframe_sec
    target = day_start + timedelta(seconds=elapsed + delta)

    return target.replace(microsecond=0)
