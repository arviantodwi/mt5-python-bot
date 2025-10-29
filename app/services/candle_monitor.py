import logging
import time
from datetime import timedelta
from typing import List, Optional

from app.adapters.mt5_client import MT5Client
from app.domain.models import Candle
from app.infra.clock import JAKARTA_TZ, now_local
from app.infra.timeframe import timeframe_to_seconds

logger = logging.getLogger(__name__)


class CandleMonitorService:
    """
    Monitors closed candles per symbol with de-duplication and gap backfill.
        - Uses integer epoch seconds from MT5 (no float equality problems).
        - If multiple bars were missed, processes them oldest -> newest.
        - Pure monitoring: logs bar summaries; no signals/trades here.
    """

    def __init__(self, mt5: MT5Client, symbol: str, bootstrap_mode: bool = True, bootstrap_bars: int = 1) -> None:
        self._mt5 = mt5
        self._timeframe_sec = timeframe_to_seconds(mt5.timeframe)
        self._bootstrap_mode = bootstrap_mode
        self._bootstrap_bars = max(1, bootstrap_bars)
        self._symbol = symbol
        self._symbol_digits: Optional[int] = None
        self._last_seen_epoch: Optional[int] = None  # epoch seconds of last processed CLOSED candle

    def process_once(self) -> None:
        self._process_symbol(self._symbol)

    # TODO Implement feature to process multi symbols
    def _process_symbol(self, symbol: str) -> None:
        MAX_SYNC_RETRIES = 3
        SYNC_SLEEP_SEC = 1

        def fetch_latest() -> Optional[tuple[int, Candle]]:
            last_candle = self._mt5.get_last_closed_candle(symbol)
            return None if not last_candle else (last_candle.epoch, last_candle)

        latest = fetch_latest()
        if not latest:
            logger.warning(f"No closed candle available for {symbol}")
            return

        last_closed_epoch, last_closed = latest

        seen = self._last_seen_epoch

        # TODO Persist last seen so bot can recover from restart
        try:
            # First run for this symbol
            if seen is None:
                if self._bootstrap_mode:
                    # Option A: process a tiny bootstrap window (1..N bars) ending at last_closed
                    start_epoch = last_closed_epoch - (self._bootstrap_bars - 1) * self._timeframe_sec
                    backfill = self._mt5.get_backfill_candles(
                        symbol, since_exclusive_epoch=start_epoch - 1, until_inclusive_epoch=last_closed_epoch
                    )
                    self._warn_if_irregular_spacing(backfill)

                    for candle in backfill:
                        self._log_candle(symbol, candle)
                        self._last_seen_epoch = candle.epoch
                else:
                    # Option B: just set the pointer; do not emit historical logs
                    self._last_seen_epoch = last_closed_epoch

                # Stabilize (initial hydration may stream more right away).
                # Minimal sync loop applied to allow MT5 to hydrate the very-latest bar.
                prev_epoch = self._last_seen_epoch

                for i in range(MAX_SYNC_RETRIES):
                    # logger.debug("Last closed candle hasn't hydrated yet (seen=%s). Retry #%d", prev_epoch, i + 1)

                    time.sleep(SYNC_SLEEP_SEC)

                    latest_to_fill = fetch_latest()
                    if not latest_to_fill:
                        break

                    new_epoch, _ = latest_to_fill

                    if prev_epoch is None or new_epoch > prev_epoch:
                        # Process the newly available span (prev_epoch, new_epoch]
                        backfill_for_span = self._mt5.get_backfill_candles(
                            symbol,
                            since_exclusive_epoch=prev_epoch or (new_epoch - self._timeframe_sec),
                            until_inclusive_epoch=new_epoch,
                        )
                        self._warn_if_irregular_spacing(backfill_for_span)

                        for candle in backfill_for_span:
                            self._log_candle(symbol, candle)
                            self._last_seen_epoch = candle.epoch

                    # Break immediately after extending
                    if self._last_seen_epoch and new_epoch == self._last_seen_epoch:
                        break

                return

            # Already up-to-date or terminal hasn't exposed new bar yet.
            # Minimal sync loop applied to allow MT5 to hydrate the very-latest bar.
            if last_closed_epoch <= seen:
                prev_epoch = seen

                for i in range(MAX_SYNC_RETRIES):
                    logger.debug("Last closed candle hasn't hydrated yet (seen=%s). Retry #%d", prev_epoch, i + 1)

                    time.sleep(SYNC_SLEEP_SEC)

                    latest_to_fill = fetch_latest()
                    if not latest_to_fill:
                        break

                    new_epoch, new_last_closed = latest_to_fill

                    if new_epoch > prev_epoch:
                        # We have a newer closed bar now -> backfill the gap
                        backfill = self._mt5.get_backfill_candles(
                            symbol, since_exclusive_epoch=prev_epoch, until_inclusive_epoch=new_epoch
                        )
                        self._warn_if_irregular_spacing(backfill)

                        if backfill:
                            for candle in backfill:
                                self._log_candle(symbol, candle)
                                self._last_seen_epoch = candle.epoch
                        else:
                            # At least process the newly closed bar
                            self._log_candle(symbol, new_last_closed)
                            self._last_seen_epoch = new_epoch

                        break

                return

            # One or more bars missing → backfill them in order
            backfill = self._mt5.get_backfill_candles(
                symbol, since_exclusive_epoch=seen, until_inclusive_epoch=last_closed_epoch
            )
            if backfill:
                self._warn_if_irregular_spacing(backfill)

                for candle in backfill:
                    self._log_candle(symbol, candle)
                    self._last_seen_epoch = candle.epoch
            else:
                # Fallback: process last_closed at least
                self._log_candle(symbol, last_closed)
                self._last_seen_epoch = last_closed_epoch

        except Exception as e:
            logger.exception(f"Monitor error for {symbol}: {e}")

    def _log_candle(self, symbol: str, candle: Candle) -> None:
        if self._symbol_digits is None:
            self._symbol_digits = self._mt5.get_symbol_meta(symbol).digits

        server_open_time = candle.time_utc
        local_open_time = server_open_time.astimezone(JAKARTA_TZ) - timedelta(hours=2)

        d = self._symbol_digits
        ohlc_format = f"%.{d}f"
        open = ohlc_format % candle.open
        high = ohlc_format % candle.high
        low = ohlc_format % candle.low
        close = ohlc_format % candle.close
        volume = candle.volume

        logger.info(
            "Candle {} {} (server: {}) closed | O={} H={} L={} C={} Volume={}".format(
                symbol,
                local_open_time.strftime("%Y-%m-%d %H:%M:%S"),
                server_open_time.strftime("%Y-%m-%d %H:%M:%S"),
                open,
                high,
                low,
                close,
                volume,
            )
        )

    def _warn_if_irregular_spacing(self, candles: List[Candle]) -> None:
        if len(candles) > 1:
            step = int((candles[1].time_utc - candles[0].time_utc).total_seconds())
            if step != self._timeframe_sec:
                logger.warning("Irregular bar spacing (expected %s seconds): %s", self._timeframe_sec, step)
