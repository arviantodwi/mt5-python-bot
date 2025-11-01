from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.adapters.mt5_client import MT5Client


@dataclass
class PositionGuardService:
    """
    Enforces one-open-position-at-a-time and a freeze window that starts AFTER position is closed.
    In v1, freeze timestamp is in-memory (resets on restart).
    """

    mt5: MT5Client
    symbol: str
    freeze_hours: Optional[float] = None

    _last_closed_at_utc: Optional[datetime] = None

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
