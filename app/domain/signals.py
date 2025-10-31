from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Bias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NONE = "NONE"


@dataclass(frozen=True)
class Signal:
    """
    Represents a trade signal tied to a specific closed candle. No execution
    details here, only produces pure detection result.
    """

    symbol: str
    side: SignalSide
    candle_time_utc: datetime
    timeframe_minutes: int
    bias: Bias
    # Optional fields to aid later execution/journaling
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    is_live: bool = True  # False when signal detected on backfilled bars
