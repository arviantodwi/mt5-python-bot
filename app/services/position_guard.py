from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.adapters.mt5_client import MT5Client
from app.config.settings import Settings
from app.domain.indicators import IndicatorsSnapshot
from app.domain.models import Candle
from app.domain.signals import SignalSide as Side
from app.infra.clock import JAKARTA_TZ
from app.services.risk import RiskService

_l = logging.getLogger(__name__)
guard_logger = logging.LoggerAdapter(_l, extra={"tag": "Guard"})


@dataclass
class PositionGuardService:
    """
    Enforces one-open-position-at-a-time and a freeze window that starts AFTER position is closed.
    In v1, freeze timestamp is in-memory (resets on restart). Also handles SL → Break-Even (commission-aware)
    once +1R progress is reached.
    """

    mt5: MT5Client
    risk: RiskService
    symbol: str
    freeze_hours: Optional[float] = None
    _last_closed_at_utc: Optional[datetime] = None
    _open_position_ticket: Optional[int] = None
    # Optional: remember when BE was armed; useful if trailing should start on the next candle
    _be_armed_at_utc: Optional[datetime] = None

    def has_open_position(self) -> bool:
        positions = self.mt5.get_positions(self.symbol)
        return len(positions) > 0

    def is_in_freeze(self, now_utc: datetime) -> bool:
        if self.freeze_hours is None:
            return False
        if self._last_closed_at_utc is None:
            return False
        return now_utc < (self._last_closed_at_utc + timedelta(minutes=self.freeze_hours * 60))

        )
    def mark_position_closed(self, closed_at_utc: datetime) -> None:
        self._last_closed_at_utc = closed_at_utc
        if self.freeze_hours is not None:
            freeze_end_time = self._last_closed_at_utc + timedelta(minutes=self.freeze_hours * 60)
            guard_logger.info(
                "Position closed. Freeze window active until %s (%.1f hours)",
                freeze_end_time.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                self.freeze_hours,
            )

    def on_closed_candle(self, candle: Candle, snapshot: IndicatorsSnapshot) -> None:
        """
        Called once per CLOSED candle. Manages position lifecycle:
        - Detects when a new position is opened and starts tracking it.
        - Detects when the tracked position is closed and triggers the freeze window.
        - If a position is open, manages break-even and trailing stop-loss adjustments.
        """
        settings = Settings.model_validate({})
        positions = self.mt5.get_positions(self.symbol)
        position_tickets = {p.ticket for p in positions}

        # State: A position was being tracked
        if self._open_position_ticket is not None:
            # Transition: Tracked position has been closed
            if self._open_position_ticket not in position_tickets:
                self.mark_position_closed(candle.time_utc + timedelta(minutes=settings.timeframe))
                self._open_position_ticket = None
                self._be_armed_at_utc = None  # Reset break-even state
                return  # No further processing needed for this candle

            # State: Tracked position is still open
            # Find the position object to proceed with in-trade management
            open_position = next((p for p in positions if p.ticket == self._open_position_ticket), None)
            if open_position:
                self._manage_in_trade_sl(open_position, candle, snapshot)

        # State: No position was being tracked
        else:
            # Transition: A new position has just been opened
            if positions:
                new_position = positions[0]
                self._open_position_ticket = new_position.ticket
                guard_logger.info("Now tracking new position with ticket: %d", new_position.ticket)

    def _manage_in_trade_sl(self, pos, candle: Candle, snapshot: IndicatorsSnapshot) -> None:
        """
        Dispatches SL management to either BE or trailing SL handlers.
        """
        settings = Settings.model_validate({})
        if not settings.enable_breakeven_sl:
            return

        if self._be_armed_at_utc is None:
            self._manage_breakeven(pos, candle)
        else:
            self._manage_trailing_sl(pos, candle, snapshot)

    def _manage_breakeven(self, pos, candle: Candle) -> None:
        """
        Moves the stop-loss to a commission-aware break-even point once +1R is reached.
        """
        settings = Settings.model_validate({})
        meta = self.mt5.get_symbol_meta(self.symbol)
        price_format = f"%.{meta.digits}f"

        side = pos.side
        entry = float(pos.price_open)
        current_sl = float(pos.sl) if pos.sl is not None else None
        current_tp = float(pos.tp) if pos.tp is not None else None
        lot = float(pos.lot)

        if current_sl is None or current_sl == 0.0:
            return

        risk_distance = abs(entry - current_sl)
        if risk_distance <= 0.0:
            return

        if settings.be_trigger_price == "close":
            move = (candle.close - entry) if side == Side.BUY else (entry - candle.close)
            if (move / risk_distance) < 1.0:
                return
        else:  # settings.be_trigger_price == "hl"
            if side == Side.BUY and candle.high < entry + risk_distance:
                return
            if side == Side.SELL and candle.low > entry - risk_distance:
                return

        be_price = self.risk.compute_be_covering_commission(
            side=side,
            entry=entry,
            lot=lot,
            digits=meta.digits,
            tick_value=meta.tick_value,
            tick_size=meta.tick_size,
            commission_per_lot=settings.commission_per_lot,
            is_round_trip=True,
        )

        min_distance = meta.stops_level * meta.tick_size
        if side == Side.BUY:
            candidate_sl = max(current_sl, be_price)
            if (candle.close - candidate_sl) < min_distance:
                candidate_sl = candle.close - min_distance

            candidate_sl = round(candidate_sl, meta.digits)
            if candidate_sl <= current_sl:
                return

            new_tp = None if settings.take_profit_mode == "trail" else current_tp
            ok = self.mt5.modify_position_sl_tp(symbol=self.symbol, sl=candidate_sl, tp=new_tp, ticket=pos.ticket)
            if ok:
                guard_logger.info(
                    "Position %d: SL moved to BE. Original: %s, New: %s",
                    pos.ticket,
                    price_format % current_sl,
                    price_format % candidate_sl,
                )
                self._be_armed_at_utc = candle.time_utc

        else:  # side == Side.SELL
            candidate_sl = min(current_sl, be_price)
            if (candidate_sl - candle.close) < min_distance:
                candidate_sl = candle.close + min_distance

            candidate_sl = round(candidate_sl, meta.digits)
            if candidate_sl >= current_sl:
                return

            new_tp = None if settings.take_profit_mode == "trail" else current_tp
            ok = self.mt5.modify_position_sl_tp(symbol=self.symbol, sl=candidate_sl, tp=new_tp, ticket=pos.ticket)
            if ok:
                guard_logger.info(
                    "Position %d: SL moved to BE. Original: %s, New: %s",
                    pos.ticket,
                    price_format % current_sl,
                    price_format % candidate_sl,
                )
                self._be_armed_at_utc = candle.time_utc

    def _manage_trailing_sl(self, pos, candle: Candle, snapshot: IndicatorsSnapshot) -> None:
        """
        Manages trailing stop-loss for a position where break-even has already been armed.
        """
        settings = Settings.model_validate({})
        if settings.take_profit_mode not in ("trail", "hybrid"):
            return
        if self._be_armed_at_utc is None or candle.time_utc <= self._be_armed_at_utc:
            return
        if snapshot.atr14 is None:
            return

        meta = self.mt5.get_symbol_meta(self.symbol)
        price_format = f"%.{meta.digits}f"
        side = pos.side
        entry = float(pos.price_open)
        current_sl = float(pos.sl) if pos.sl is not None else None
        current_tp = float(pos.tp) if pos.tp is not None else None
        lot = float(pos.lot)

        if current_sl is None or current_sl == 0.0:
            return

        trail_multiplier = settings.atr_trail_multiplier
        if trail_multiplier <= 0.0:
            return

        trail_distance = snapshot.atr14 * trail_multiplier
        min_distance = meta.stops_level * meta.tick_size

        be_price = self.risk.compute_be_covering_commission(
            side=side,
            entry=entry,
            lot=lot,
            digits=meta.digits,
            tick_value=meta.tick_value,
            tick_size=meta.tick_size,
            commission_per_lot=settings.commission_per_lot,
            is_round_trip=True,
        )

        if side == Side.BUY:
            candidate_sl = max(be_price, candle.close - trail_distance)
            if (candle.close - candidate_sl) < min_distance:
                candidate_sl = max(be_price, candle.close - min_distance)

            candidate_sl = round(candidate_sl, meta.digits)
            if candidate_sl <= current_sl or (candidate_sl - current_sl) < meta.tick_size:
                return

            new_tp = None if settings.take_profit_mode == "trail" else current_tp
            ok = self.mt5.modify_position_sl_tp(symbol=self.symbol, sl=candidate_sl, tp=new_tp, ticket=pos.ticket)
            if ok:
                guard_logger.info("Position %d: Trailing SL updated to %s", pos.ticket, price_format % candidate_sl)
        else:
            candidate_sl = min(be_price, candle.close + trail_distance)
            if (candidate_sl - candle.close) < min_distance:
                candidate_sl = min(be_price, candle.close + min_distance)

            candidate_sl = round(candidate_sl, meta.digits)
            if candidate_sl >= current_sl or (current_sl - candidate_sl) < meta.tick_size:
                return

            new_tp = None if settings.take_profit_mode == "trail" else current_tp
            ok = self.mt5.modify_position_sl_tp(symbol=self.symbol, sl=candidate_sl, tp=new_tp, ticket=pos.ticket)
            if ok:
                guard_logger.info("Position %d: Trailing SL updated to %s", pos.ticket, price_format % candidate_sl)
