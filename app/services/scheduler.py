from datetime import timedelta

from app.infra.clock import (
    JAKARTA_TZ,
    SessionWindow,
    in_session,
    next_m5_close,
    next_session_start,
    now_local,
    sleep_until,
)
from app.infra.logging import logging

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Session-aware scheduler that:
        - runs only Mon to Fri, 07:00 to 24:00 (Asia/Jakarta)
        - wakes just after each 5-minute candle close (1s buffer added here)
        - calls a user-provided "on_tick" callable
    """
    def __init__(self, window: SessionWindow, buffer_seconds: float = 1.0) -> None:
        self.window = window
        self.buffer_seconds = buffer_seconds

    def run_forever(self, on_candle_close) -> None:
        """
        on_candle_close(): callable with no args (it captures symbols/services)
        """
        while True:
            now = now_local(JAKARTA_TZ)

            if not in_session(now, self.window):
                start = next_session_start(now, self.window)
                logger.info(f"Out of session. Sleeping until next session start: {start.strftime('%Y-%m-%d %H:%M:%S')}")
                sleep_until(start)
                continue

            # Inside session. Align to next 5-minute candle close, add small buffer, then call
            target = next_m5_close(now).replace(second=0, microsecond=0)
            target_with_buff = target + timedelta(seconds=self.buffer_seconds)
            logger.debug(f"Sleeping until next 5-minute candle close: {target_with_buff.strftime('%Y-%m-%d %H:%M:%S')}")
            sleep_until(target_with_buff)

            try:
                on_candle_close()
            except Exception as e:
                logger.exception(f"on_candle_close failed: {e}")
