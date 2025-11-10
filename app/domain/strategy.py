from __future__ import annotations

import logging
from typing import Deque, Iterable, Optional, cast

from app.domain.indicators import IndicatorsSnapshot
from app.domain.models import Candle
from app.domain.signals import Bias, Signal, SignalSide

_l = logging.getLogger(__name__)
strategy_logger = logging.LoggerAdapter(_l, extra={"tag": "Strategy"})


def compute_bias(close: float, ema200: Optional[float]) -> Bias:
    """
    Return trend bias given close vs EMA200. If EMA200 is None, returns NONE.
    """
    if ema200 is None:
        return Bias.NONE
    if close > ema200:
        return Bias.BULLISH
    if close < ema200:
        return Bias.BEARISH
    # Default return
    return Bias.NONE


def is_doji(candle: Candle, ratio: float) -> bool:
    """
    Doji calculation is: abs(close-open) <= ratio * (high - low).
    If high == low, return True only when close == open (flat tick).
    """
    range = max(candle.high - candle.low, 0.0)
    body = abs(candle.close - candle.open)
    if range == 0.0:
        return body == 0.0
    return body <= ratio * range


def strictly_monotonic(values: Iterable[float], increasing: bool) -> bool:
    """
    True if values are strictly increasing or strictly decreasing.
    """
    iterator = iter(values)
    try:
        prev = next(iterator)
    except StopIteration:
        return False

    for value in iterator:
        if increasing and not (value > prev):
            return False
        if not increasing and not (value < prev):
            return False
        prev = value

    return True


def detect_pattern_and_signal(
    symbol: str,
    timeframe_minutes: int,
    window4: Deque[Candle],  # oldest -> newest (len==4)
    snaps4: Deque[IndicatorsSnapshot],  # aligned oldest -> newest (len==4)
    doji_ratio: float,
    is_live_bar: bool,
) -> Optional[Signal]:
    """
    Apply strategy rules on a 4-candle window aligned with 4 indicator snapshots.
    Returns a Signal if all conditions met. Otherwise, None.
    """

    if len(window4) < 4 or len(snaps4) < 4:
        return None

    c1, c2, c3, c4 = window4
    s1, s2, s3, s4 = snaps4

    # Indicators must be ready across the window: EMA200 & MACD histogram available
    if any(s.ema200 is None or s.histogram is None for s in (s1, s2, s3, s4)):
        strategy_logger.debug("Signal rejected: Indicators not ready.")
        return None

    # Determine bias using the last candle's close vs EMA200 (most recent snapshot)
    bias = compute_bias(c4.close, s4.ema200)
    if bias == Bias.NONE:
        return None

    # Candlestick color pattern
    def is_bear(candle: Candle) -> bool:
        return candle.close < candle.open

    def is_bull(candle: Candle) -> bool:
        return candle.close > candle.open

    # Close-on-close monotonicity
    closes = (c1.close, c2.close, c3.close, c4.close)

    # Helper to count candles based on the given condition
    def _count(condition, candles):
        return sum(1 for c in candles if condition(c))

    # MACD histogram monotonicity over the same window
    hist_values = (s1.histogram, s2.histogram, s3.histogram, s4.histogram)
    if any(value is None for value in hist_values):
        return None
    # Redefine hist_values so all tuple items have a float type
    hist_values = (
        cast(float, s1.histogram),
        cast(float, s2.histogram),
        cast(float, s3.histogram),
        cast(float, s4.histogram),
    )

    # Doji allowance among c2..c4, at most one doji
    doji_count = sum(1 for c in (c2, c3, c4) if is_doji(c, doji_ratio))
    if doji_count > 1:
        strategy_logger.debug("Signal rejected: More than one Doji candle found in the pattern.")
        return None

    # Branch by bias with pattern rules
    if bias == Bias.BULLISH:
        # c1 must be bearish
        if not is_bear(c1):
            strategy_logger.debug("Signal rejected: Bullish bias but C1 candle was not bearish.")
            return None
        # among c2..c4, all non-doji must be bullish
        if _count(lambda x: (not is_doji(x, doji_ratio)) and (not is_bull(x)), (c2, c3, c4)) > 0:
            return None
        # closes strictly increasing; histogram strictly increasing
        if not strictly_monotonic(closes, increasing=True):
            strategy_logger.debug("Signal rejected: Closes were not strictly increasing.")
            return None
        if not strictly_monotonic(hist_values, increasing=True):
            strategy_logger.debug("Signal rejected: MACD Histogram were not strictly increasing.")
            return None
        side = SignalSide.BUY
    else:  # Bias.BEARISH
        # c1 must be bullish
        if not is_bull(c1):
            strategy_logger.debug("Signal rejected: Bearish bias but C1 candle was not bullish.")
            return None
        # among c2..c4, all non-doji must be bearish
        if _count(lambda x: (not is_doji(x, doji_ratio)) and (not is_bear(x)), (c2, c3, c4)) > 0:
            return None
        # closes strictly decreasing; histogram strictly decreasing
        if not strictly_monotonic(closes, increasing=False):
            strategy_logger.debug("Signal rejected: Closes were not strictly decreasing.")
            return None
        if not strictly_monotonic(hist_values, increasing=False):
            strategy_logger.debug("Signal rejected: MACD Histogram were not strictly decreasing.")
            return None
        side = SignalSide.SELL

    return Signal(
        symbol=symbol,
        side=side,
        candle_time_utc=c4.time_utc,  # signal confirmed on 4th candle close
        timeframe_minutes=timeframe_minutes,
        bias=bias,
        is_live=is_live_bar,
    )
