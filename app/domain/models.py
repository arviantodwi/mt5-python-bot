from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    time_utc: datetime
    epoch: int
    open: float
    high: float
    low: float
    close: float
    volume: float
