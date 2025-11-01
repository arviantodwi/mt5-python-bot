from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from app.domain.models import SymbolMeta


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

        return (round(lot, 2), risk_used)  # MT5 usually accepts 2 decimals for FX; adjust if your symbols differ

    @staticmethod
    def _floor_to_step(lot: float, step: float) -> float:
        if step <= 0:
            return lot
        return math.floor(lot / step) * step
