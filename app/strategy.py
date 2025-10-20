from typing import Literal

import pandas as pd
from talib import CDLDOJI as Doji
from talib import CDLLONGLEGGEDDOJI as LongLeggedDoji


class Strategy:
    def __init__(self, df: pd.DataFrame, order_type: Literal["buy", "sell"]) -> None:
        self.bars = df.copy(deep=True).reset_index(drop=True).tail(14)
        self.retracement_slope = None
        self.confidence_rate = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.trend_bias = None

        if order_type == "buy":
            self.three_bars_pattern = self.__is_rising_three_pattern(self.bars)
        else:
            self.three_bars_pattern = self.__is_falling_three_pattern(self.bars)

    def __compute_confidence_rate(self, order_type: Literal["buy", "sell"]) -> None:
        if self.three_bars_pattern is not None:
            self.confidence_rate += 1

        if self.retracement_slope is not None:
            self.confidence_rate += 1

    def __is_rising_three_pattern(self, df: pd.DataFrame) -> bool:
        df["is_doji"] = self.__is_doji_bar(df)

        four_bars = df.tail(4)
        first_bar = four_bars.iloc[0]
        second_bar = four_bars.iloc[1]
        third_bar = four_bars.iloc[2]
        fourth_bar = four_bars.iloc[3]

        # Detects whether a rising pattern is forming from the last 4 bars:
        is_first_bar_bearish = first_bar["open"] > first_bar["close"] and not first_bar["is_doji"]
        is_last_3_bars_bullish = (
            (second_bar["open"] < second_bar["close"] and not second_bar["is_doji"])
            and (third_bar["open"] < third_bar["close"] and not third_bar["is_doji"])
            and (fourth_bar["open"] < fourth_bar["close"] and not fourth_bar["is_doji"])
            and second_bar["close"] < third_bar["close"] < fourth_bar["close"]
        )
        is_valid_pattern = is_first_bar_bearish and is_last_3_bars_bullish

        if is_valid_pattern:
            print("\nRising Three Pattern detected")
            print(f"Bottom price (open of first bullish bar): {second_bar['open']}")
            print(f"Top price (close of last bullish bar): {fourth_bar['close']}")
            print(f"Mean price (stop loss): {(second_bar['open'] + fourth_bar['close']) / 2}")

        return is_valid_pattern

    def __is_falling_three_pattern(self, df: pd.DataFrame) -> bool:
        df["is_doji"] = self.__is_doji_bar(df)

        four_bars = df.tail(4)
        first_bar = four_bars.iloc[0]
        second_bar = four_bars.iloc[1]
        third_bar = four_bars.iloc[2]
        fourth_bar = four_bars.iloc[3]

        # Detects whether a falling pattern is forming from the last 4 bars:
        is_first_bar_bullish = first_bar["open"] < first_bar["close"] and not first_bar["is_doji"]
        is_last_3_bars_bearish = (
            (second_bar["open"] > second_bar["close"] and not second_bar["is_doji"])
            and (third_bar["open"] > third_bar["close"] and not third_bar["is_doji"])
            and (fourth_bar["open"] > fourth_bar["close"] and not fourth_bar["is_doji"])
            and second_bar["close"] > third_bar["close"] > fourth_bar["close"]
        )
        is_valid_pattern = is_first_bar_bullish and is_last_3_bars_bearish

        if is_valid_pattern:
            print("\nFalling Three Pattern detected")
            print(f"Top price (open of first bearish bar): {second_bar['open']}")
            print(f"Bottom price (close of last bearish bar): {fourth_bar['close']}")
            print(f"Mean price (stop loss): {(second_bar['open'] + fourth_bar['close']) / 2}")

        return is_valid_pattern

        # is_three_black_crows = (
        #     # All are bearish candles (close is lower than open)
        #     (first_bar["open"] > first_bar.close)
        #     and (second_bar["open"] > second_bar.close)
        #     and (third_bar["open"] > third_bar.close)
        #     # Each closes lower than the previous
        #     and (first_bar.close > second_bar.close > third_bar.close)
        #     # Second opens within the body of the first
        #     and (second_bar["open"] < first_bar["open"] and second_bar["open"] > first_bar.close)
        #     # Third opens within the body of the second
        #     and (third_bar["open"] < second_bar["open"] and third_bar["open"] > second_bar.close)
        # )

    def __is_doji_bar(self, df: pd.DataFrame):
        open, high, low, close = df[["open", "high", "low", "close"]].values.T
        is_regular_doji = Doji(open, high, low, close).astype(bool)
        is_long_legged_doji = LongLeggedDoji(open, high, low, close).astype(bool)

        return is_regular_doji | is_long_legged_doji

    def __compute_retracement_slope(self, df: pd.DataFrame, count: int = 7):
        pass
