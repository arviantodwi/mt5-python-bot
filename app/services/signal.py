from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from app.domain.indicators import IndicatorsSnapshot
from app.domain.models import Candle
from app.domain.signals import Signal
from app.domain.strategy import detect_pattern_and_signal

logger = logging.getLogger(__name__)


@dataclass
class _Buffer:
    candles: Deque[Candle]
    snaps: Deque[IndicatorsSnapshot]


class SignalService:
    """
    Maintains sliding windows and produces Signals based on the last 4 closed candles
    and aligned indicator snapshots.
    """

    def __init__(self, symbol: str, timeframe_minutes: int, doji_ratio: float = 0.1) -> None:
        self._symbol = symbol
        self._timeframe_minutes = timeframe_minutes
        self._doji_ratio = doji_ratio
        self._buffer = _Buffer(candles=deque(maxlen=4), snaps=deque(maxlen=4))

    def on_closed(self, candle: Candle, snapshot: IndicatorsSnapshot, is_live_bar: bool) -> Optional[Signal]:
        """Consume one closed candle + its indicators snapshot and maybe emit a Signal."""
        self._buffer.candles.append(candle)
        self._buffer.snaps.append(snapshot)

        if len(self._buffer.candles) < 4:
            return None

        signal = detect_pattern_and_signal(
            symbol=self._symbol,
            timeframe_minutes=self._timeframe_minutes,
            window4=self._buffer.candles,
            snaps4=self._buffer.snaps,
            doji_ratio=self._doji_ratio,
            is_live_bar=is_live_bar,
        )

        if signal:
            # Log at INFO for visibility
            freshness = "LIVE" if signal.is_live else "STALE"
            logger.info(
                "Signal %s %s at %s (%s)",
                signal.side.value,
                signal.symbol,
                signal.candle_time_utc.strftime("%Y-%m-%d %H:%M:%S"),
                freshness,
            )

        return signal
