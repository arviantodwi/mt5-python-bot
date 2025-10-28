import time
from typing import Dict

from app.adapters.mt5_client import MT5Client
from app.domain.models import Candle
from app.infra.logging import logging

logger = logging.getLogger(__name__)

MAX_SYNC_RETRIES = 3
SYNC_SLEEP_SEC = 0.2


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
            seen = self._last_seen_epoch.get(symbol)

            def fetch_latest() -> tuple[int, Candle] | None:
                return self._mt5.get_last_closed_candle(symbol, self._timeframe)

            latest = fetch_latest()
            if not latest:
                logger.warning(f"No closed candle available for {symbol}")
                return

            last_closed_epoch, last_closed = latest

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

                # Stabilize history right now (extra pulls if MT5 loads more)
                prev_epoch = last_closed_epoch
                for _ in range(MAX_SYNC_RETRIES):
                    time.sleep(SYNC_SLEEP_SEC)
                    latest2 = fetch_latest()
                    if not latest2:
                        break
                    new_epoch, _ = latest2
                    if new_epoch <= prev_epoch:
                        break
                    # Process the newly available span (prev_epoch, new_epoch]
                    backfill2 = self._mt5.get_backfill_candles(
                        symbol, self._timeframe, since_exclusive_epoch=prev_epoch, until_inclusive_epoch=new_epoch
                    )
                    for bar in backfill2:
                        self._log_candle(symbol, bar)
                        self._last_seen_epoch[symbol] = int(bar.time_utc.timestamp())
                    prev_epoch = new_epoch
                return

            # Already up-to-date
            if last_closed_epoch <= seen:
                # Minimal sync loop to allow MT5 to hydrate the very-latest bar
                prev_epoch = seen
                for i in range(MAX_SYNC_RETRIES):
                    logger.debug(f"Last closed candle hasn't hydrated yet. Attempting retry: `{i + 1}`.")

                    time.sleep(SYNC_SLEEP_SEC)
                    latest2 = self._mt5.get_last_closed_candle(symbol, self._timeframe)
                    if not latest2:
                        break

                    new_epoch, new_last_closed = latest2
                    if new_epoch > prev_epoch:
                        # We have a newer closed bar now → backfill the gap
                        backfill2 = self._mt5.get_backfill_candles(
                            symbol, self._timeframe, since_exclusive_epoch=prev_epoch, until_inclusive_epoch=new_epoch
                        )
                        if backfill2:
                            for bar in backfill2:
                                self._log_candle(symbol, bar)
                                self._last_seen_epoch[symbol] = int(bar.time_utc.timestamp())
                        else:
                            # At least process the newly closed bar
                            self._log_candle(symbol, new_last_closed)
                            self._last_seen_epoch[symbol] = new_epoch
                        break
                # Either we processed the newly appeared bar(s) or nothing changed—return.
                return

            # One or more bars missing → backfill them in order
            backfill = self._mt5.get_backfill_candles(
                symbol, self._timeframe, since_exclusive_epoch=seen, until_inclusive_epoch=last_closed_epoch
            )
            if backfill:
                for candle in backfill:
                    self._log_candle(symbol, candle)
                    self._last_seen_epoch[symbol] = int(candle.time_utc.timestamp())
            else:
                # Fallback: process last_closed at least
                self._log_candle(symbol, last_closed)
                self._last_seen_epoch[symbol] = last_closed_epoch

            # Stabilize: MT5 may expose still more history immediately after
            prev_epoch = self._last_seen_epoch[symbol]
            for _ in range(MAX_SYNC_RETRIES):
                time.sleep(SYNC_SLEEP_SEC)
                latest2 = fetch_latest()
                if not latest2:
                    break
                new_epoch, _ = latest2
                if new_epoch <= prev_epoch:
                    break
                backfill2 = self._mt5.get_backfill_candles(
                    symbol, self._timeframe, since_exclusive_epoch=prev_epoch, until_inclusive_epoch=new_epoch
                )
                if not backfill2:
                    break
                for bar in backfill2:
                    self._log_candle(symbol, bar)
                    self._last_seen_epoch[symbol] = int(bar.time_utc.timestamp())
                prev_epoch = self._last_seen_epoch[symbol]

        except Exception as e:
            logger.exception(f"Monitor error for {symbol}: {e}")

    def _log_candle(self, symbol: str, candle: Candle) -> None:
        logger.info(
            f"Candle {symbol} {candle.time_utc.strftime('%Y-%m-%d %H:%M:%S')} closed | O={candle.open} H={candle.high} L={candle.low} C={candle.close} Volume={candle.volume}"
        )
