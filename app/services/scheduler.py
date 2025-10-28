from __future__ import annotations

import logging
from datetime import timedelta

from app.infra.clock import SessionWindow, in_session, next_aligned_close, next_session_start, now_local, sleep_until

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Session-aware scheduler that:
        - runs only within the SessionWindow (supports overnight windows, Mon-Fri)
        - wakes just after each TF close (buffer seconds)
        - calls a user-provided callback per close
    """

    def __init__(self, window: SessionWindow, timeframe: int, buffer_seconds: float = 1.0) -> None:
        self.window = window
        self.timeframe = timeframe
        self.buffer_seconds = buffer_seconds

    def run_forever(self, on_candle_close) -> None:
        """
        on_candle_close(): callable with no args (it captures symbols/services)
        """
        while True:
            now = now_local(self.window.tz)

            if not in_session(now, self.window):
                start = next_session_start(now, self.window)
                logger.info(f"Out of session. Sleeping until next session start: {start.strftime('%Y-%m-%d %H:%M:%S')}")
                sleep_until(start)
                logger.info(f"Start of today's session: {start.strftime('%Y-%m-%d %H:%M:%S')}")
                continue

            # Inside session. Align to next 5-minute candle close, add small buffer, then call
            target = next_aligned_close(now, self.timeframe)
            target_with_buff = target + timedelta(seconds=self.buffer_seconds)
            logger.debug(
                "Sleeping until next {} candle close: {}".format(
                    self._humanize_timeframe(self.timeframe), target_with_buff.strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            sleep_until(target_with_buff)

            try:
                on_candle_close()
            except Exception as e:
                logger.exception(f"on_candle_close failed: {e}")

    def _humanize_timeframe(self, minutes: int) -> str:
        """
        Converts an integer representing minutes into a human-readable,
        hyphenated string format (e.g., "5-minute", "1-hour", "2-day").

        Args:
            minutes: The duration in minutes.

        Returns:
            A formatted string.
        """
        if minutes <= 0:
            return "invalid-duration"

        # Define constants for clarity
        MINUTES_IN_HOUR = 60
        MINUTES_IN_DAY = MINUTES_IN_HOUR * 24  # 1440

        if minutes % MINUTES_IN_DAY == 0:
            # Check for days. We check if it's perfectly divisible by MINUTES_IN_DAY.
            value = minutes // MINUTES_IN_DAY
            unit = "day"
        elif minutes % MINUTES_IN_HOUR == 0:
            # Check for hours. We check if it's perfectly divisible by MINUTES_IN_HOUR.
            value = minutes // MINUTES_IN_HOUR
            unit = "hour"
        else:
            # Default to minutes
            value = minutes
            unit = "minute"

        return f"{value}-{unit}"
