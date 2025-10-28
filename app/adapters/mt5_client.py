from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import mt5_wrapper as mt5

from app.domain.models import Candle

from .mt5_utils import parse_mt5_version, with_mt5_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolMeta:
    name: str
    digits: int
    tick_size: float
    tick_value: float
    lot_step: float
    min_lot: float
    stops_level: int
    freeze_level: int


class MT5Client:
    """
    Thin wrapper around MetaTrader5.* functions. Keeps MT5-specific calls in one
    place so the rest of the app stays decoupled.
    """

    def __init__(self, login: int, password: str, server: str, terminal_path: str | None) -> None:
        self._login = login
        self._password = password
        self._server = server
        self._terminal_path = terminal_path
        self._initialized = False
        atexit.register(self.shutdown)

    def initialize(self) -> None:
        if self._initialized:
            return
        if not mt5.initialize(self._terminal_path, timeout=5_000, portable=False):
            raise RuntimeError(with_mt5_error("MT5 initialize failed."))

        authorized = mt5.login(self._login, self._password, self._server, timeout=5_000)
        if not authorized:
            mt5.shutdown()
            raise RuntimeError(with_mt5_error("MT5 login failed."))

        self._initialized = True
        logger.debug(f"Connected to MT5 terminal version {parse_mt5_version(mt5.version())}")
        logger.info(f'MT5 initialized and logged in to server "{self._server}" as login {self._login}')

    def shutdown(self) -> None:
        if self._initialized:
            try:
                mt5.shutdown()
            finally:
                self._initialized = False
                logger.info("MT5 shutdown complete.")

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MT5 is not initialized.")

    def ensure_symbol_selected(self, symbol: str) -> None:
        self._ensure_initialized()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol {symbol} not found on server")

        if not info.visible:
            if not mt5.symbol_select(symbol, enabled=True):
                raise RuntimeError(f"Cannot select symbol {symbol}")

        logger.debug(f"Symbol ensured: {symbol}")

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        self._ensure_initialized()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol {symbol} not found on server")

        return SymbolMeta(
            name=info.name,
            digits=info.digits,
            tick_size=info.point,
            tick_value=info.trade_tick_value,
            lot_step=info.volume_step,
            min_lot=info.volume_min,
            stops_level=info.trade_stops_level,
            freeze_level=info.trade_freeze_level,
        )

    def get_last_closed_candle(self, symbol: str, timeframe: int) -> Optional[Tuple[int, Candle]]:
        """
        Return the last CLOSED candle as Candle, or None if unavailable.
        Uses copy_rates_from_pos(symbol, timeframe, start_pos, count).
        We request the last 2 bars and take index [-2] to ensure closed.
        """
        self._ensure_initialized()
        rates = mt5.copy_rates_from_pos(symbol, timeframe, start_pos=0, count=2)
        if rates is None or len(rates) < 2:
            return None

        last_closed = rates[-2]  # Ensure closed bar
        epoch = int(last_closed["time"])  # MT5 gives POSIX seconds (UTC), already int
        time_utc = datetime.fromtimestamp(epoch, tz=timezone.utc)

        candle = Candle(
            time_utc,
            float(last_closed["open"]),
            float(last_closed["high"]),
            float(last_closed["low"]),
            float(last_closed["close"]),
            volume=float(last_closed["tick_volume"]),
        )

        return epoch, candle

    def get_backfill_candles(
        self, symbol: str, timeframe: int, since_exclusive_epoch: int, until_inclusive_epoch: int
    ) -> List[Candle]:
        """
        Fetch all CLOSED bars with time in (since_exclusive_epoch, ..., until_inclusive_epoch].
        Uses copy_rates_range for clarity. Returns bars in ascending time order.
        """
        if until_inclusive_epoch <= since_exclusive_epoch:
            return []

        # MT5 copy_rates_range expects datetimes (UTC)
        start = datetime.fromtimestamp(since_exclusive_epoch + 1, tz=timezone.utc)
        end = datetime.fromtimestamp(until_inclusive_epoch + 1, tz=timezone.utc)
        rates = mt5.copy_rates_range(symbol, timeframe, start, end)
        if rates is None or len(rates) == 0:
            return []

        bars = []
        for rate in rates:
            epoch = int(rate["time"])
            time_utc = datetime.fromtimestamp(epoch, tz=timezone.utc)

            if since_exclusive_epoch < epoch <= until_inclusive_epoch:
                bars.append(
                    Candle(
                        time_utc,
                        float(rate["open"]),
                        float(rate["high"]),
                        float(rate["low"]),
                        float(rate["close"]),
                        float(rate["tick_volume"]),
                    )
                )

        # MT5 usually returns ascending, but ensure ordering
        bars.sort(key=lambda candle: int(candle.time_utc.timestamp()))
        return bars
