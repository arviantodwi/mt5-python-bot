from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SymbolMeta:
    name: str
    digits: int
    tick_size: float
    tick_value: float
    lot_step: float
    min_lot: float
    stops_level: int
    freeze_level: int


@dataclass(frozen=True)
class Candle:
    time_utc: datetime
    epoch: int
    open: float
    high: float
    low: float
    close: float
    volume: float
