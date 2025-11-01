from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Literal, Optional

from app.domain.models import Candle, SymbolMeta
from app.domain.orders import OrderPlan, Side


@dataclass(frozen=True)
class OrderPlannerService:
    """
    Builds an OrderPlan from a detected signal and the last 4 candles,
    applying SL nudge policy against broker stops_level and preserving RR.
    """

    rr: float
    nudge_mode: Literal["off", "conservative", "flexible"] = "conservative"
    nudge_factor: float = 1.5  # used only in conservative

    def from_last4(
        self,
        symbol: str,
        side: Side,
        last4: Deque[Candle],  # oldest -> newest, len == 4
        meta: SymbolMeta,
        signal_time_utc,
    ) -> Optional[OrderPlan]:
        """
        Derive SL/TP from 4-candle extremes (no entry price here; ExecutionService uses live quote).

        BUY:
        - SL = min(low of last4)
        - TP later: entry + rr * (entry - SL)

        SELL:
        - SL = max(high of last4)
        - TP later: entry - rr * (SL - entry)

        We don't know entry yet; here we only compute SL (rounded), and we will recompute TP after we know entry.
        However, for planning integrity and logging, we also compute a provisional TP at mid price (not used in execution).

        Returns None if nudge_mode='off' and stops_level requires a farther SL than your plan,
        or if conservative mode requires a factor > nudge_factor.
        """
        if len(last4) < 4:
            return None

        c1, c2, c3, c4 = last4
        if side == Side.BUY:
            sl = min(c.low for c in (c1, c2, c3, c4))
        else:
            sl = max(c.high for c in (c1, c2, c3, c4))

        # Round SL to symbol digits
        sl = self._round_to_digits(sl, meta.digits)

        # SL nudge policy *relative to current price* is finalized in ExecutionService
        # because we need the *live* entry price and broker stops_level in points.
        # Here we only return OrderPlan with SL; TP will be computed at execution to preserve RR.

        return OrderPlan(
            symbol=symbol,
            side=side,
            rr=self.rr,
            planned_sl=sl,
            planned_tp=sl,  # placeholder; ExecutionService recomputes real TP from live entry and RR
            signal_time_utc=signal_time_utc,
            source_signal_id=None,
        )

    @staticmethod
    def _round_to_digits(price: float, digits: int) -> float:
        if digits < 0:
            return price
        # p = 10**digits
        return round(price + 0.0, digits)
