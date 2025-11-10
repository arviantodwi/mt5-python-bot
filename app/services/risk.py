from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Tuple

from app.domain.models import SymbolMeta
from app.domain.orders import Side

_l = logging.getLogger(__name__)
risk_logger = logging.LoggerAdapter(_l, extra={"tag": "Risk"})


@dataclass(frozen=True)
class RiskService:
    """
    Computes position size (lot) based on account balance, risk percentage, broker tick specs,
    and the distance between entry and stop-loss.
    """

    risk_percentage: float  # e.g. 0.01 (1%)

    def compute_lot(
        self,
        balance: float,
        entry_price: float,
        stop_loss: float,
        meta: SymbolMeta,
    ) -> Tuple[float, float]:
        """
        Returns (lot, risk_used). Always floors the lot to the broker step and ensures risk_used ≤ risk_target.
        - tick_value is the cash value per one tick_size move for 1.0 lot.
        - stop distance is measured in ticks (points = price_diff / tick_size).
        """

        d = meta.digits
        price_format = f"%.{d}f"
        risk_logger.debug(
            "Computing lot: balance=%.2f, entry=%s, stop_loss=%s",
            balance,
            price_format % entry_price,
            price_format % stop_loss,
        )

        risk_target = max(0.0, balance * self.risk_percentage)
        if risk_target <= 0:
            return 0.0, 0.0

        price_diff = abs(entry_price - stop_loss)
        ticks = price_diff / meta.tick_size if meta.tick_size > 0 else 0.0
        # Risk per 1.0 lot in currency units
        risk_per_lot = ticks * meta.tick_value

        if risk_per_lot <= 0.0:
            return 0.0, 0.0

        raw_lot = risk_target / risk_per_lot

        lot = self._floor_to_step(raw_lot, meta.lot_step)
        lot = max(lot, meta.min_lot)

        # Ensure risk_used ≤ risk_target; decrement if needed
        risk_used = lot * risk_per_lot
        while lot > meta.min_lot and risk_used > risk_target + 1e-9:
            lot = round(lot - meta.lot_step, 8)
            if lot < meta.min_lot:
                lot = meta.min_lot
                break
            risk_used = lot * risk_per_lot

        risk_logger.debug("Computed lot: lot=%.2f, risk_used=%.2f", lot, risk_used)

        # Round display/adapter precision to the symbol's lot_step decimals
        digits = self._decimals_from_step(meta.lot_step)
        return (round(lot, digits), risk_used)

    def compute_be_covering_commission(
        self,
        side: Side,
        entry: float,
        lot: float,
        digits: int,
        tick_value: float,
        tick_size: float,
        commission_per_lot: Optional[float],
        is_round_trip: Optional[bool],
    ):
        """
        Break-even price that covers both single and round-trip commissions. Assumes
        `commission_per_lot` is PER SIDE (common), so round-trip total is equal to
        2 * commission_per_lot * volume.

        If commission_per_lot is None => treated as 0.0.
        """
        per_side = commission_per_lot or 0.0
        total_commission = per_side * lot
        if is_round_trip:
            total_commission *= 2.0

        # PnL per 1.0 price unit for given lot:
        # 1 price unit = (1 / tick_size) ticks; PnL per lot per unit = tick_value / tick_size
        pnl_per_unit = lot * (tick_value / tick_size)
        if pnl_per_unit <= 0:
            return entry

        offset = total_commission / pnl_per_unit  # price units to cover fees

        price_format = f"%.{digits}f"
        risk_logger.debug(
            "Break-even calculation: commission_cost=%.2f, price_offset=%s",
            total_commission,
            price_format % offset,
        )

        if side == Side.BUY:
            return entry + offset
        else:
            return entry - offset

    @staticmethod
    def _floor_to_step(lot: float, step: float) -> float:
        if step <= 0:
            return lot
        return math.floor(lot / step) * step

    @staticmethod
    def _decimals_from_step(step: float) -> int:
        """
        Compute number of decimals required by the lot step, e.g.:
        1.0 -> 0, 0.1 -> 1, 0.01 -> 2, 0.001 -> 3
        """
        s = f"{step:.10f}".rstrip("0")
        if "." not in s:
            return 0
        return len(s.split(".")[1])
