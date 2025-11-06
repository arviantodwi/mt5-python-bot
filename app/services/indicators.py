from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional

from app.domain.indicators import AtrState, EmaState, IndicatorsSnapshot, MacdState
from app.domain.models import Candle

logger = logging.getLogger(__name__)


@dataclass
class _InternalState:
    """Holds mutable running indicator states and counters."""

    ema200: EmaState
    macd: MacdState
    atr14: AtrState
    n_closes: int
    last_histogram: Deque[Optional[float]]


class IndicatorsService:
    """
    Maintains streaming EMA(200), MACD(12,26,9) histogram, and ATR(14) values. This service:
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
            atr14=AtrState.empty(14),
            n_closes=0,
            last_histogram=deque(maxlen=max(1, histogram_window)),
        )

    def warmup_with_candles(self, candles: Iterable[Candle]) -> None:
        """
        Feed a historical sequence of CLOSED candles to pre-seed indicators.

        Notes:
            - Provide candles oldest → newest.
            - For full readiness, at least 200 bars are needed for EMA200, ~35 for MACD histogram, and 14 for ATR(14).
        """
        for candle in candles:
            self._consume_candle(candle)

    def on_closed_candle(self, candle: Candle) -> IndicatorsSnapshot:
        """Consume one CLOSED candle and return the latest indicators snapshot."""
        return self._consume_candle(candle)

    def _consume_candle(self, candle: Candle) -> IndicatorsSnapshot:
        """
        Update internal EMA/MACD/ATR states with a new CLOSED candle and return a snapshot.
        EMA/MACD use close; ATR uses high/low/close (True Range with gaps).
        """
        state = self._state
        state.n_closes += 1

        high = candle.high
        low = candle.low
        close = candle.close

        # EMA 200 (close-only)
        n_ema200 = state.ema200.update(close)

        # MACD(12,26,9) (close-only)
        n_macd, macd, signal, histogram = state.macd.update(close)

        # ATR(14) (high/low/close)
        n_atr14 = state.atr14.update(high, low, close)

        # Maintain histogram window
        state.last_histogram.append(histogram)

        # Replace state
        state.ema200 = n_ema200
        state.macd = n_macd
        state.atr14 = n_atr14

        # Readiness counters (non-negative)
        # EMA200: SMA seeding of 200 closes
        bars_until_ema200 = max(0, 200 - state.n_closes)

        # MACD histogram readiness: ~26 (EMA26 seed) + ~9 (signal seed) ≈ 35 closes
        bars_until_histogram = max(0, 35 - state.n_closes)

        # ATR(14): when seeding, AtrState.value is None and its internal _seed holds TRs so far
        if n_atr14.value is None:
            # NOTE: AtrState stores seeding TRs in `_seed`. Length is how many TRs collected.
            seed_len = len(n_atr14._seed)
            bars_until_atr14 = max(0, n_atr14.period - seed_len)
        else:
            bars_until_atr14 = 0

        return IndicatorsSnapshot(
            ema200=n_ema200.value,
            macd=macd,
            signal=signal,
            histogram=histogram,
            atr14=n_atr14.value,
            bars_until_ready_ema200=bars_until_ema200,
            bars_until_ready_macd_histogram=bars_until_histogram,
            bars_until_ready_atr14=bars_until_atr14,
            last_histogram_values=deque(state.last_histogram, maxlen=state.last_histogram.maxlen),
        )
