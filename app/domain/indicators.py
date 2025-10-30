from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple


@dataclass(frozen=True)
class EmaState:
    """
    Streaming EMA state container.

    Attributes:
        period (int)           : EMA period (e.g., 200).
        value (Optional[float]): Current EMA value; None until seeded.
        _seed (List[float])    : Internal seeding buffer for SMA; empty after the first EMA is established.
    """

    period: int
    value: Optional[float]
    _seed: List[float]

    @staticmethod
    def empty(period: int) -> EmaState:
        """Create an empty EMA state with the given period and no seed."""
        return EmaState(period, value=None, _seed=[])

    def update(self, close: float) -> EmaState:
        """Consume a new close and return the next EMA state."""
        ema, seed = _ema_seed_or_update(close, self.period, self.value, list(self._seed))
        return EmaState(self.period, value=ema, _seed=seed)


@dataclass(frozen=True)
class MacdState:
    """
    Streaming MACD state for (12, 26, 9) setup. Maintains:
    - ema12, ema26 over closes
    - signal9 over MACD line
    - histogram = macd - signal (None until signal seeded)

    The first MACD value is available once both ema12 and ema26 are seeded.
    The histogram is available once the signal9 is seeded.

    Attributes:
        ema12 (EmaState)  : Stream of EMA 12 state.
        ema26 (EmaState)  : Stream of EMA 26 state.
        signal9 (EmaState): Stread of EMA 9 state as MACD signal.
    """

    ema12: EmaState
    ema26: EmaState
    signal9: EmaState

    @staticmethod
    def empty() -> MacdState:
        """Create an empty MACD(12,26,9) state."""
        return MacdState(EmaState.empty(12), EmaState.empty(26), EmaState.empty(9))

    def update(self, close: float) -> Tuple[MacdState, Optional[float], Optional[float], Optional[float]]:
        """Consume a new close and return (new_state, macd, signal, histogram)."""
        new_ema12 = self.ema12.update(close)
        new_ema26 = self.ema26.update(close)

        macd: Optional[float] = None
        if new_ema12.value is not None and new_ema26.value is not None:
            macd = new_ema12.value - new_ema26.value

        # Update signal EMA on MACD values (only when macd exists)
        new_signal = self.signal9
        if macd is not None:
            new_signal = self.signal9.update(macd)

        histogram: Optional[float] = None
        if macd is not None and new_signal.value is not None:
            histogram = macd - new_signal.value

        return MacdState(new_ema12, new_ema26, new_signal), macd, new_signal.value, histogram


@dataclass(frozen=True)
class IndicatorsSnapshot:
    """
    Immutable snapshot of current indicators for one closed candle.

    Attributes:
        ema200 (Optional[float])                 : EMA(200) over closes. None until seeded.
        macd (Optional[float])                   : MACD line value (ema12 - ema26). None until seeded.
        signal (Optional[float])                 : Signal line (EMA9 of MACD). None until seeded.
        hist (Optional[float])                   : MACD histogram (macd - signal). None until seeded.
        bars_until_ready_ema200 (int)            : Number of additional bars required until EMA200 becomes available.
        bars_until_ready_macd_hist (int)         : Number of additional bars required until MACD histogram becomes available.
        last_hist_values (Deque[Optional[float]]): Rolling window of last N histogram values (oldest → newest). useful later for trend checks.
    """

    ema200: Optional[float]
    macd: Optional[float]
    signal: Optional[float]
    histogram: Optional[float]
    bars_until_ready_ema200: int
    bars_until_ready_macd_histogram: int
    last_histogram_values: Deque[Optional[float]]


def _alpha(period: int) -> float:
    """Return EMA smoothing factor a = 2 / (period + 1)."""
    if period <= 0:
        raise ValueError("Period must be greater than 0")
    return 2.0 / (period + 1.0)


def _ema_seed_or_update(
    close: float, period: int, prev_ema: Optional[float], seed_buff: List[float]
) -> Tuple[Optional[float], List[float]]:
    """
    Update an EMA stream with either seeding-by-SMA (if prev_ema is None) or the standard EMA step.

    Parameters:
        x (float)                 : New input value (e.g., close price).
        period (int)              : EMA period (e.g., 200).
        prev_ema (Optional[float]): Previous EMA value; if None, we are still seeding.
        seed_buf (List[float])    : Buffer of values collected for SMA seeding. Will be consumed when its len reaches `period`.

    Returns:
        (ema, seed_buff) (Tuple[Optional[float], List[float]]):
            - ema is None until the seeding buffer reaches `period`.
            - once seeded, returns the SMA as the first EMA and clears the buffer.
            - after seeding, returns the updated EMA each call and leaves buffer empty.
    """
    if prev_ema is None:
        seed_buff.append(close)
        if len(seed_buff) < period:
            return None, seed_buff
        if len(seed_buff) == period:
            # First EMA = SMA of the first `period` values.
            first = float(sum(seed_buff)) / float(period)
            return first, []

    # Standard EMA update
    a = _alpha(period)
    ema = a * close + (1.0 - a) * (prev_ema if prev_ema is not None else close)
    return ema, seed_buff
