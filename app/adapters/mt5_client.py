from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Literal, Optional

import mt5_wrapper as mt5
from mt5_wrapper import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TRADE_ACTION_DEAL

from app.domain.models import Candle, SymbolMeta
from app.domain.signals import SignalSide as Side
from app.infra.timeframe import humanize_mt5_timeframe

from .mt5_utils import parse_mt5_version, with_mt5_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    time_utc: datetime


@dataclass(frozen=True)
class OpenPosition:
    ticket: int
    symbol: str
    side: Side
    lot: float
    price_open: float
    time_utc: datetime


@dataclass(frozen=True)
class OrderSendResult:
    status: Literal["FILLED", "REJECTED", "ERROR"]
    ticket: int
    entry_price: float
    stop_loss: float
    take_profit: float
    time_utc: datetime
    reason: Optional[str] = None


class MT5Client:
    """
    Thin wrapper around MetaTrader5.* functions. Keeps MT5-specific calls in one
    place so the rest of the app stays decoupled.
    """

    # Current support only from 1-minute to 4-hour timeframe
    _MINUTE_TO_MT5_TIMEFRAME = {
        1: mt5.TIMEFRAME_M1,
        2: mt5.TIMEFRAME_M2,
        3: mt5.TIMEFRAME_M3,
        5: mt5.TIMEFRAME_M5,
        10: mt5.TIMEFRAME_M10,
        15: mt5.TIMEFRAME_M15,
        30: mt5.TIMEFRAME_M30,
        60: mt5.TIMEFRAME_H1,
        120: mt5.TIMEFRAME_H2,
        180: mt5.TIMEFRAME_H3,
        240: mt5.TIMEFRAME_H4,
        # 1440: mt5.TIMEFRAME_D1,
        # 10080: mt5.TIMEFRAME_W1,
        # 43200: mt5.TIMEFRAME_MN1,
    }

    _TIMEFRAME_FALLBACK = mt5.TIMEFRAME_M5

    def __init__(self, login: int, password: str, server: str, terminal_path: str | None) -> None:
        self._login = login
        self._password = password
        self._server = server
        self._terminal_path = terminal_path
        self._initialized = False
        self.timeframe = self._TIMEFRAME_FALLBACK
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

    def _tf_to_mt5(self, minutes: int) -> int:
        timeframe = self._MINUTE_TO_MT5_TIMEFRAME.get(minutes)
        if timeframe is None:
            logger.warning(f"Unsupported timeframe minutes: {minutes}. Fallback to {self._TIMEFRAME_FALLBACK} minutes.")
            timeframe = self._TIMEFRAME_FALLBACK
        return timeframe

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MT5 is not initialized.")

    def ensure_timeframe(self, minutes: int) -> None:
        self._ensure_initialized()
        timeframe = self._tf_to_mt5(minutes)
        self.timeframe = timeframe
        logger.debug(f"Timeframe ensured: {humanize_mt5_timeframe(timeframe)}")

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

        tick_value = info.trade_tick_value
        if symbol == "XAUUSD" and info.trade_tick_value == 10.0:
            # Empirically adjust tick_value to 1.0 to match account contract size
            logger.warning("Adjusting XAUUSD tick_value from 10.0 → 1.0 for accurate lot sizing.")
            tick_value = 1.0

        return SymbolMeta(
            name=info.name,
            digits=info.digits,
            tick_size=info.point,
            tick_value=tick_value,
            lot_step=info.volume_step,
            min_lot=info.volume_min,
            stops_level=info.trade_stops_level,
            freeze_level=info.trade_freeze_level,
        )

    def prime_history(self, symbol: str, count: int = 1500) -> None:
        """Optional: trigger terminal to hydrate recent history quickly."""
        self._ensure_initialized()
        try:
            mt5.copy_rates_from_pos(symbol, self.timeframe, 0, count)
            logger.debug("History primed for %s (%d bars)", symbol, count)
        except Exception:
            pass

    def get_last_closed_candle(self, symbol: str) -> Optional[Candle]:
        """
        Return the last CLOSED candle as Candle, or None if unavailable.
        Uses copy_rates_from_pos(symbol, timeframe, start_pos, count).
        We request the last 2 bars and take index [-2] to ensure closed.
        """
        self._ensure_initialized()
        rates = mt5.copy_rates_from_pos(symbol, self.timeframe, start_pos=0, count=2)
        if rates is None or len(rates) < 2:
            return None

        last_closed = rates[-2]  # Ensure closed bar
        epoch = int(last_closed["time"])  # MT5 gives POSIX seconds (UTC), already int
        time_utc = datetime.fromtimestamp(epoch, tz=timezone.utc)

        return Candle(
            time_utc,
            epoch,
            float(last_closed["open"]),
            float(last_closed["high"]),
            float(last_closed["low"]),
            float(last_closed["close"]),
            volume=float(last_closed["tick_volume"]),
        )

    def get_backfill_candles(self, symbol: str, since_exclusive_epoch: int, until_inclusive_epoch: int) -> List[Candle]:
        """
        Fetch all CLOSED bars with time in (since_exclusive_epoch, ..., until_inclusive_epoch].
        Uses copy_rates_range for clarity. Returns bars in ascending time order.
        """
        self._ensure_initialized()

        if until_inclusive_epoch <= since_exclusive_epoch:
            return []

        # MT5 copy_rates_range expects datetimes (UTC)
        start = datetime.fromtimestamp(since_exclusive_epoch + 1, tz=timezone.utc)
        end = datetime.fromtimestamp(until_inclusive_epoch + 1, tz=timezone.utc)
        rates = mt5.copy_rates_range(symbol, self.timeframe, start, end)
        if rates is None or len(rates) == 0:
            return []

        candles: List[Candle] = []
        for rate in rates:
            epoch = int(rate["time"])
            if since_exclusive_epoch < epoch <= until_inclusive_epoch:
                time_utc = datetime.fromtimestamp(epoch, tz=timezone.utc)
                candles.append(
                    Candle(
                        time_utc,
                        epoch,
                        float(rate["open"]),
                        float(rate["high"]),
                        float(rate["low"]),
                        float(rate["close"]),
                        float(rate["tick_volume"]),
                    )
                )

        # MT5 usually returns ascending, but ensure ordering
        candles.sort(key=lambda candle: int(candle.time_utc.timestamp()))
        return candles

    def get_quote(self, symbol: str) -> Optional[Quote]:
        info = mt5.symbol_info_tick(symbol)
        if info is None:
            return None
        # mt5 returns time in seconds since 1970 (broker/server), treat as UTC
        time_utc = datetime.fromtimestamp(info.time, tz=timezone.utc)
        return Quote(bid=float(info.bid), ask=float(info.ask), time_utc=time_utc)

    def get_account_balance(self) -> float:
        account = mt5.account_info()
        return float(account.balance) if account else 0.0

    def get_positions(self, symbol: str) -> List[OpenPosition]:
        rows = mt5.positions_get(symbol=symbol) or []
        out: List[OpenPosition] = []
        for position in rows:
            out.append(
                OpenPosition(
                    ticket=int(position.ticket),
                    symbol=position.symbol,
                    side=Side.BUY if int(position.type) == 0 else Side.SELL,
                    lot=float(position.volume),
                    price_open=float(position.price_open),
                    time_utc=datetime.fromtimestamp(int(position.time), tz=timezone.utc),
                )
            )
        return out

    def send_market_order(
        self,
        symbol: str,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        deviation: int = 10,
    ) -> Optional[OrderSendResult]:
        """
        Sends a market order with SL/TP. Returns OrderSendResult or None on MT5 error.
        """

        order_type = ORDER_TYPE_BUY if side == Side.BUY else ORDER_TYPE_SELL

        request = {
            "action": TRADE_ACTION_DEAL,
            "symbol": symbol,
            "type": order_type,
            "volume": float(volume),
            "deviation": int(deviation),
            "sl": float(sl),
            "tp": float(tp),
        }

        response = mt5.order_send(request)
        if response is None:
            return None

        # Map result
        # response.retcode == 10009 (done) on MetaTrader5; adjust mapping for your wrapper
        status = "FILLED" if getattr(response, "retcode", 0) in (10009,) else "REJECTED"
        reason = getattr(response, "comment", None)
        entry = getattr(response, "price", 0.0)
        ticket = getattr(response, "order", 0)
        time_utc = datetime.now(tz=timezone.utc)

        return OrderSendResult(
            status=status,
            ticket=int(ticket),
            entry_price=float(entry),
            stop_loss=float(sl),
            take_profit=float(tp),
            time_utc=time_utc,
            reason=reason,
        )
