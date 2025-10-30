from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional

from app.domain.indicators import EmaState, IndicatorsSnapshot, MacdState
from app.domain.models import Candle

logger = logging.getLogger(__name__)


@dataclass
class _InternalState:
    """Holds mutable running indicator states and counters."""

    ema200: EmaState
    macd: MacdState
    n_closes: int
    last_histogram: Deque[Optional[float]]


class IndicatorsService:
    """
    Maintains streaming EMA(200) and MACD(12,26,9) histogram values. This service:
    - is broker-agnostic (no adapter import);
    - accepts candles/closes in chronological order (closed bars only);
    - supports optional warm-up via `warmup_with_candles` so indicators are ready from the first live tick.

    Examples:
    ```python
    svc = IndicatorsService()
    svc.warmup_with_candles(recent_candles)  # optional, recommended (≥ 200 bars)
    snapshot = svc.on_closed_candle(candle)
    if snapshot.hist is not None:
        ...  # ready
    ```
    """

    def __init__(self, histogram_window: int = 4) -> None:
        self._state = _InternalState(
            ema200=EmaState.empty(200),
            macd=MacdState.empty(),
            n_closes=0,
            last_histogram=deque(maxlen=max(1, histogram_window)),
        )

    def warmup_with_candles(self, candles: Iterable[Candle]) -> None:
        """
        Feed a historical sequence of CLOSED candles to pre-seed EMA200 and MACD.

        Notes:
            - Provide candles oldest → newest.
            - For full readiness, at least 200 bars are needed for EMA200, and ~35 for MACD histogram.
        """
        for candle in candles:
            self._consume_close(candle.close)

    def on_closed_candle(self, candle: Candle) -> IndicatorsSnapshot:
        """Consume one CLOSED candle and return the latest indicators snapshot."""
        return self._consume_close(candle.close)

    def _consume_close(self, close: float) -> IndicatorsSnapshot:
        """Update internal EMA/MACD states with a new close value and return a snapshot."""
        state = self._state
        state.n_closes += 1

        # EMA 200
        n_ema200 = state.ema200.update(close)

        # MACD(12,26,9)
        n_macd, macd, signal, histogram = state.macd.update(close)

        # Maintain histogram window
        state.last_histogram.append(histogram)

        # Replace state
        state.ema200 = n_ema200
        state.macd = n_macd

        # Readiness counters (non-negative)
        bars_until_ema200 = max(0, 200 - state.n_closes)
        # MACD histogram readiness: need 26 to seed EMA26, then ~9 MACD values -> ~35 total
        bars_until_histogram = max(0, 35 - state.n_closes)

        return IndicatorsSnapshot(
            ema200=n_ema200.value,
            macd=macd,
            signal=signal,
            histogram=histogram,
            bars_until_ready_ema200=bars_until_ema200,
            bars_until_ready_macd_histogram=bars_until_histogram,
            last_histogram_values=deque(state.last_histogram, maxlen=state.last_histogram.maxlen),
        )
