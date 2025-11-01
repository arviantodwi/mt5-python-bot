from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from .signals import SignalSide as Side


@dataclass(frozen=True)
class OrderPlan:
    """
    Immutable plan produced from a signal before execution.
    Prices are already rounded to symbol digits and validated against the SL nudge policy.
    Lot is not set here (depends on live quote/entry). ExecutionService fills it via RiskService.

    Attributes:
        symbol (str)                    : Trading symbol.
        side (SignalSide)               : Direction.
        rr (float)                      : Risk-to-reward ratio.
        planned_sl (float)              : Planned Stop Loss price (already nudged if policy allows).
        planned_tp (float)              : Planned Take Profit price (recomputed to preserve RR if SL was nudged).
        signal_time_utc (datetime)      : The candle close time when the signal was confirmed.
        source_signal_id (Optional[str]): If we track IDs in SignalService; else keep None.
    """

    symbol: str
    side: Side
    rr: float
    planned_sl: float
    planned_tp: float
    signal_time_utc: datetime
    source_signal_id: Optional[str] = None


@dataclass(frozen=True)
class OrderResult:
    """
    Execution result returned by the adapter via ExecutionService.
    """

    symbol: str
    side: Side
    lot: float
    entry_price: float
    stop_loss: float
    take_profit: float
    ticket: int
    time_utc: datetime
    status: Literal["FILLED", "REJECTED", "ERROR"]
    reason: Optional[str] = None
