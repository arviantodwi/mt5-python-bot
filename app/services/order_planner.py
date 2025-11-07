from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Optional

from app.config.settings import Settings
from app.domain.indicators import IndicatorsSnapshot
from app.domain.models import Candle, SymbolMeta
from app.domain.orders import OrderPlan, Side


@dataclass(frozen=True)
class OrderPlannerService:
    """
    Builds an OrderPlan from a detected signal and the last 4 candles,
    applying SL nudge policy against broker stops_level and preserving RR.
    """

    rr: float

    def build_from_last4(
        self,
        symbol: str,
        side: Side,
        last4: Deque[Candle],  # oldest -> newest, len == 4
        meta: SymbolMeta,
        signal_time_utc: datetime,
        indicators: Optional[IndicatorsSnapshot] = None,
        price_ref: Optional[float] = None,  # reference price for ATR widening (defaults to c4.close)
    ) -> Optional[OrderPlan]:
        """
        Derive the planned SL from 4-candle extremes, then (optionally) widen the SL using ATR(14)
        so that the stop distance is at least `atr_sl_multiplier * ATR`.

        BUY:
        - SL = min(low of last4)
        - TP later: entry + rr * (entry - SL)

        SELL:
        - SL = max(high of last4)
        - TP later: entry - rr * (SL - entry)

        Notes:
        - Widening only: never tighten the SL relative to the chosen reference price.
        - Reference price defaults to the last closed candle's close (`c4.close`).
        - TP is left as placeholder; ExecutionService will compute the real TP from live entry.

        Returns None if input is invalid `(len(last4) < 4)`. Does not enforce `stops_level` here.
        """
        if len(last4) < 4:
            return None

        c1, c2, c3, c4 = last4

        # Baseline SL from pattern extremes
        if side == Side.BUY:
            sl = min(c.low for c in (c1, c2, c3, c4))
        else:
            sl = max(c.high for c in (c1, c2, c3, c4))

        # Round baseline SL to symbol digits
        sl = self._round_to_digits(sl, meta.digits)

        # Optional ATR-based widening (never tighten)
        # Use c4.close as the default reference for distance check
        entry_ref = c4.close if price_ref is None else price_ref
        sl = self._apply_atr_widening(side, sl, entry_ref, indicators, meta)

        return OrderPlan(
            symbol=symbol,
            side=side,
            rr=self.rr,
            planned_sl=sl,
            planned_tp=sl,  # placeholder; ExecutionService recomputes real TP from live entry and RR
            signal_time_utc=signal_time_utc,
            source_signal_id=None,
        )

    def _apply_atr_widening(
        self,
        side: Side,
        sl: float,
        entry_ref: float,
        indicators: Optional[IndicatorsSnapshot],
        meta: SymbolMeta,
    ) -> float:
        """
        Ensure `SL distance >= atr_sl_multiplier x ATR(14)`, using `entry_ref` as distance anchor.
        Widen only; never tighten. Returns the (possibly widened) SL rounded to symbol digits.
        """
        settings = Settings()  # type: ignore

        # Validate ATR availability and multiplier
        k = max(0.0, float(settings.atr_sl_multiplier))
        if indicators is None or indicators.atr14 is None or k <= 0.0:
            return sl

        atr_distance = indicators.atr14 * k
        base_distance = abs(entry_ref - sl)

        # If base distance already sufficient, keep SL unchanged
        if base_distance >= atr_distance:
            return sl

        # Otherwise widen away from entry_ref
        if side == Side.BUY:
            widened_sl = entry_ref - atr_distance
        else:
            widened_sl = entry_ref + atr_distance

        # Round to symbol digits
        widened_sl = self._round_to_digits(widened_sl, meta.digits)

        # Double-check we didn't accidentally tighten due to rounding (extremely rare)
        if abs(entry_ref - widened_sl) < base_distance:
            return sl  # fallback: keep original

        return widened_sl

    @staticmethod
    def _round_to_digits(price: float, digits: int) -> float:
        """Round price to the given number of symbol digits."""
        return price if digits < 0 else round(price, digits)
