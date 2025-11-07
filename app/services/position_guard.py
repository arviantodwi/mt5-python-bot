from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.adapters.mt5_client import MT5Client
from app.config.settings import Settings
from app.domain.indicators import IndicatorsSnapshot
from app.domain.models import Candle
from app.domain.signals import SignalSide as Side
from app.services.risk import RiskService


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
        return now_utc < (self._last_closed_at_utc + timedelta(hours=self.freeze_hours))

    def mark_position_closed(self, closed_at_utc: datetime) -> None:
        self._last_closed_at_utc = (
            closed_at_utc.replace(tzinfo=timezone.utc) if closed_at_utc.tzinfo is None else closed_at_utc
        )

    # TODO: Simplify method
    def on_closed_candle(self, candle: Candle, snapshot: IndicatorsSnapshot) -> None:
        """
        Called once per CLOSED candle.
        If ENABLE_BREAKEVEN_SL is True and the open position has progressed to +1R,
        move SL to the commission-aware break-even price (respecting broker stops_level and symbol digits).
        """
        settings = Settings()  # type: ignore

        # Feature gate
        if not settings.enable_breakeven_sl:
            return

        # Single-symbol policy; fetch open position (if any)
        positions = self.mt5.get_positions(self.symbol)
        if not positions:
            return
        pos = positions[0]  # first/only position for this symbol

        # Derive side, entry, current SL/TP, lot
        side = pos.side
        entry = float(pos.price_open)
        current_sl = float(pos.sl) if pos.sl is not None else None
        current_tp = float(pos.tp) if pos.tp is not None else None
        lot = float(pos.lot)

        # Without a valid current SL, cannot measure R progress safely
        if current_sl is None or current_sl == 0.0:
            return

        # Risk (R) = abs(entry - original/current SL)
        risk_distance = abs(entry - current_sl)
        if risk_distance <= 0.0:
            return

        if settings.be_trigger_price == "close":
            # Progress in R using CLOSED price
            if side == Side.BUY:
                move = candle.close - entry
            else:
                move = entry - candle.close
            r_progress = move / risk_distance

            if r_progress < 1.0:
                return  # Not yet at +1R
        else:
            # Progress in R using EXTREME price (high/low)
            if side == Side.BUY:
                reached_one_r = candle.high >= entry + risk_distance
            else:
                reached_one_r = candle.low <= entry - risk_distance

            if not reached_one_r:
                return  # No BE trigger yet

        # Build commission-aware break-even price
        meta = self.mt5.get_symbol_meta(self.symbol)
        be_price = self.risk.compute_be_covering_commission(
            side=side,
            entry=entry,
            lot=lot,
            tick_value=meta.tick_value,
            tick_size=meta.tick_size,
            commission_per_lot=settings.commission_per_lot,
            is_round_trip=True,  # assume per-side commission → cover round trip (if set)
        )

        # Respect broker minimum distance (stops_level)
        min_distance = meta.stops_level * meta.tick_size

        # Propose new SL in the protective direction only (never loosen)
        if side == Side.BUY:
            candidate_sl = max(current_sl, be_price)
            # Ensure (close - sl) >= min_distance
            if (candle.close - candidate_sl) < min_distance:
                candidate_sl = candle.close - min_distance
            # Round to symbol digits
            candidate_sl = round(candidate_sl, meta.digits)
            # Only improve (raise SL for BUY)
            if candidate_sl > current_sl:
                ok = self.mt5.modify_position_sl_tp(
                    symbol=self.symbol, sl=candidate_sl, tp=current_tp, ticket=pos.ticket
                )
                if ok:
                    self._be_armed_at_utc = candle.time_utc
        else:
            candidate_sl = min(current_sl, be_price)
            # Ensure (sl - close) >= min_distance
            if (candidate_sl - candle.close) < min_distance:
                candidate_sl = candle.close + min_distance
            candidate_sl = round(candidate_sl, meta.digits)
            # Only improve (lower SL for SELL)
            if candidate_sl < current_sl:
                ok = self.mt5.modify_position_sl_tp(
                    symbol=self.symbol, sl=candidate_sl, tp=current_tp, ticket=pos.ticket
                )
                if ok:
                    self._be_armed_at_utc = candle.time_utc

        # Trailing SL starts on candle after BE armed
        # Mode gate: only for 'trail' or 'hybrid'
        if settings.take_profit_mode not in ("trail", "hybrid"):
            return
        # Require: BE already armed on a previous candle
        if self._be_armed_at_utc is None or candle.time_utc <= self._be_armed_at_utc:
            return
        # Require: ATR(14) available
        if snapshot.atr14 is None:
            return

        # Trail distance from ATR
        trail_multiplier = settings.atr_trail_multiplier
        if trail_multiplier <= 0.0:
            return
        trail_distance = snapshot.atr14 * trail_multiplier

        # Broker constraints
        min_distance = meta.stops_level * meta.tick_size

        # BE clamp (never trail past BE in the wrong direction)
        if side == Side.BUY:
            # Propose candidate from current close minus trail distance, but not below BE
            candidate_sl = max(be_price, candle.close - trail_distance)
            # Respect minimum broker distance
            if (candle.close - candidate_sl) < min_distance:
                candidate_sl = max(be_price, candle.close - min_distance)
            # Round to symbol precision
            candidate_sl = round(candidate_sl, meta.digits)
            # Never loosen: only tighten upward
            if current_sl is not None and candidate_sl <= current_sl:
                return
            # Optional: skip micro-changes (< 1 tick)
            if current_sl is not None and (candidate_sl - current_sl) < meta.tick_size:
                return
            ok = self.mt5.modify_position_sl_tp(
                symbol=self.symbol,
                sl=candidate_sl,
                tp=current_tp if settings.take_profit_mode == "hybrid" else None,
                ticket=pos.ticket,
            )
            if ok:
                # (no change to _be_armed_at_utc; trailing can continue each candle)
                pass
        else:
            # SELL: close + trail; clamp above to BE
            candidate_sl = min(be_price, candle.close + trail_distance)
            if (candidate_sl - candle.close) < min_distance:
                candidate_sl = min(be_price, candle.close + min_distance)
            candidate_sl = round(candidate_sl, meta.digits)
            # Never loosen: only tighten downward
            if current_sl is not None and candidate_sl >= current_sl:
                return
            if current_sl is not None and (current_sl - candidate_sl) < meta.tick_size:
                return
            ok = self.mt5.modify_position_sl_tp(
                symbol=self.symbol,
                sl=candidate_sl,
                tp=current_tp if settings.take_profit_mode == "hybrid" else None,
                ticket=pos.ticket,
            )
            if ok:
                pass
