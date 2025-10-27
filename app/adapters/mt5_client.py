from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass

import mt5_wrapper as mt5

from .mt5_utils import with_mt5_error

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
