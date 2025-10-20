from typing import Literal

import mt5_wrapper as mt5
import numpy as np
import pandas as pd
import pandas_ta as ta


class Trading:
    """Convenience wrapper around MT5 for a single symbol/timeframe.

    Initializes symbol context, derives tick information, and loads the
    most recent 1,000 bars from MT5 (skipping the current forming bar).
    It then computes EMA(200) on close and stores a prepared DataFrame in
    `self.bars` with:
        - `time` converted to UTC `datetime`
        - an extra `ema200` column rounded up to one more decimal than the symbol's price precision.

    Attributes:
        symbol: Symbol name (e.g., "EURUSD").
        timeframe: MT5 timeframe constant (e.g., `mt5.TIMEFRAME_M5`).
        tick_info: Dict with `decimals`, `tick_size` (smallest tick size), and `tick_value` (value per tick for one lot).
        bars: Pandas DataFrame of recent bars including the `ema200` column.

    Notes:
        The helper `get_order_type()` returns "long" when the last close is
        above `ema200`, "short" when below, or `None` if equal.
    """

    def __init__(self, symbol: str, timeframe: int) -> None:
        """Initialize trading context for a symbol and timeframe."""

        self.symbol = symbol
        self.timeframe = timeframe

        # Fetch symbol info from MT5. Raise a runtime error if no info is found.
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            raise RuntimeError(f"{symbol} info is empty.")

        # Store symbol's decimal precision, tick size and value per tick as a dictionary.
        symbol_digits = symbol_info.digits
        symbol_contract_size = symbol_info.trade_contract_size
        tick_size = 1 / (10**symbol_digits)
        tick_value = tick_size * symbol_contract_size
        self.tick_info = dict(decimals=symbol_digits, tick_size=tick_size, tick_value=tick_value)

        # Fetch the latest 1,000 bar rates from MT5. Raise a runtime error if no
        # rates are returned.
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 1, 1000)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"{symbol} rates is empty.")

        # Store the rates DataFrame, including derived time and an additional
        # EMA-200 column.
        df = pd.DataFrame(rates)
        ema200 = ta.ema(df["close"], length=200)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df["ema200"] = self.__round_up_ema_decimals(ema200)
        self.bars = df

    def append_bars(self, count: int = 1) -> pd.DataFrame:
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 1, count)
        df = pd.DataFrame(rates)

        # Derive time value
        df["time"] = pd.to_datetime(df["time"], unit="s")

        # Compute current EMA-200 value
        # last_ema200 = self.bars["ema200"].iloc[-1]
        # ema200_alpha_factor = 2 / (200 + 1)
        # current_close_price = df["close"].iloc[0]
        # current_ema200 = (current_close_price * ema200_alpha_factor) + (last_ema200 * (1 - ema200_alpha_factor))
        # df["ema200"] = self.__round_up_ema_decimals(current_ema200)

        # Append current bar into existing bars dataframe
        df = pd.concat([self.bars.iloc[1:], df], ignore_index=True)

        # Recompute EMA-200 column
        ema200 = ta.ema(df["close"], length=200)
        df["ema200"] = self.__round_up_ema_decimals(ema200)

        self.bars = df

        return df

    def get_order_type(self) -> Literal["buy", "sell"] | None:
        close, ema200 = self.bars.tail(1)[["close", "ema200"]].iloc[0]
        # ema200_value = self.bars["ema200"].iloc[0]

        return "buy" if close > ema200 else "sell" if close < ema200 else None

    def post_buy_order():
        pass

    def post_sell_order():
        pass

    def __compute_lot_size(self, entry_price: int, stop_loss: int, tick_value_per_lot: int):
        pass

    def __round_up_ema_decimals(self, ema: pd.Series):
        ema_decimals = self.tick_info["decimals"] + 1
        decimal_scale = 10**ema_decimals
        return np.ceil(ema * decimal_scale) / decimal_scale
