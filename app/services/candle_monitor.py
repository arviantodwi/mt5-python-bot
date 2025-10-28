from typing import Dict, Optional, Tuple

from app.adapters.mt5_client import MT5Client
from app.domain.models import Candle
from app.infra.clock import JAKARTA_TZ
from app.infra.logging import logging

logger = logging.getLogger(__name__)


class CandleMonitorService:
    """
    Monitors closed candles per symbol with de-duplication and gap backfill.
        - Uses integer epoch seconds from MT5 (no float equality problems).
        - If multiple bars were missed, processes them oldest -> newest.
        - Pure monitoring: logs bar summaries; no signals/trades here.
    """

    def __init__(self, mt5: MT5Client, timeframe: int, bootstrap_mode: bool = True, bootstrap_bars: int = 1) -> None:
        self._mt5 = mt5
        self._timeframe = timeframe
        self._timeframe_sec = timeframe * 60
        self._last_seen_epoch: Dict[str, int] = {}  # symbol -> epoch seconds of last processed CLOSED bar
        self._bootstrap_mode = bootstrap_mode
        self._bootstrap_bars = max(1, bootstrap_bars)

    def process_symbol(self, symbol: str) -> None:
        # TODO Implement feature to process multi symbols
        try:
            last_two = self._mt5.get_last_closed_candle(symbol, self._timeframe)
            if not last_two:
                logger.warning(f"No closed candle available for {symbol}")
                return

            last_closed_epoch, last_closed = last_two
            seen = self._last_seen_epoch.get(symbol)

            # First run for this symbol
            if seen is None:
                if self._bootstrap_mode:
                    # Option A: process a tiny bootstrap window (1..N bars) ending at last_closed
                    start_epoch = last_closed_epoch - (self._bootstrap_bars - 1) * self._timeframe_sec
                    backfill = self._mt5.get_backfill_candles(
                        symbol,
                        self._timeframe,
                        since_exclusive_epoch=start_epoch - 1,
                        until_inclusive_epoch=last_closed_epoch,
                    )
                    for candle in backfill:
                        self._log_candle(symbol, candle)
                        self._last_seen_epoch[symbol] = int(candle.time_utc.timestamp())
                else:
                    # Option B: just set the pointer; do not emit historical logs
                    self._last_seen_epoch[symbol] = last_closed_epoch
                return

            # Already up-to-date
            if last_closed_epoch <= seen:
                return

            # One or more bars missing → backfill them in order
            backfill = self._mt5.get_backfill_candles(
                symbol, self._timeframe, since_exclusive_epoch=seen, until_inclusive_epoch=last_closed_epoch
            )
            if not backfill:
                # Fallback: process last_closed at least
                self._log_candle(symbol, last_closed)
                self._last_seen_epoch[symbol] = last_closed_epoch
                return

            for candle in backfill:
                self._log_candle(symbol, candle)
                self._last_seen_epoch[symbol] = int(candle.time_utc.timestamp())

        except Exception as e:
            logger.exception(f"Monitor error for {symbol}: {e}")

    def _log_candle(self, symbol: str, candle: Candle) -> None:
        logger.info(
            f"Candle {symbol} {candle.time_utc.strftime('%Y-%m-%d %H:%M:%S')} closed | O={candle.open} H={candle.high} L={candle.low} C={candle.close} Volume={candle.volume}"
        )
