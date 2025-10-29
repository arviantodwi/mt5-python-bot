from __future__ import annotations

import logging
from datetime import timedelta

from app.infra.clock import SessionWindow, in_session, next_session_start, now_local, sleep_until
from app.infra.timeframe import humanize_timeframe, next_aligned_close

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
                    humanize_timeframe(self.timeframe), target_with_buff.strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            sleep_until(target_with_buff)

            try:
                on_candle_close()
            except Exception as e:
                logger.exception(f"on_candle_close failed: {e}")
