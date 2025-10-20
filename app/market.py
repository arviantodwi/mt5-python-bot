import time
from datetime import datetime, timezone
from multiprocessing import connection, current_process

import mt5_wrapper as mt5
import pandas as pd
import pandas_ta as ta

from .helper import clear_and_print, colorize_text, with_tag


class Market:
    def __init__(self, symbol: str, timeframe: int, poll_interval: int):
        self.symbol = symbol
        self.timeframe = timeframe
        self.poll_interval = poll_interval
        self.rates = fetch_rates(symbol, timeframe, 1000)


def fetch_rates(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"{symbol} rates is empty.")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def market_watch_worker(conn: connection.Connection, symbol: str, timeframe: int, poll_interval: int):
    p = current_process()
    first_run = True

    # Important to re-init mt5 in child process, so the process can call the
    # mt5 library functions.
    mt5.initialize()

    try:
        while p.is_alive():
            if first_run:
                first_run = False
            else:
                time.sleep(poll_interval)

            print(fetch_rates(symbol, timeframe, 1))

            # conn.send(f"symbol: {self.symbol}, timeframe: {self.timeframe}, poll interval: {self.poll_interval}")

            # tick = mt5.symbol_info_tick(self.symbol)
            # if not tick:
            #     raise RuntimeError(f"Failed to retrieve {self.symbol} info tick.")

            # server_now = datetime.fromtimestamp(tick.time, tz=timezone.utc)
            # server_time = server_now.strftime("%H:%M")
            # # adjusted_ask = "{:.{}f}".format(tick.ask, trade.tick_info["decimals"])
            # adjusted_ask = "{:.{}f}".format(tick.ask, 2)
            # # adjusted_bid = "{:.{}f}".format(tick.bid, trade.tick_info["decimals"])
            # adjusted_bid = "{:.{}f}".format(tick.bid, 2)
            # adjusted_ema200 = "{:.{}f}".format(trade.bars.tail(1)["ema200"].iloc[0], trade.tick_info["decimals"] + 1)

            # clear_and_print(
            #     f"[{server_time}] Ask={adjusted_ask}, Bid={adjusted_bid}, EMA200={adjusted_ema200}, Order Type={trade.get_order_type() or 'n/a'}",
            #     end="\r",
            #     flush=True,
            # )

            # # Check if current bar in the selected timeframe is still running or has already closed.
            # # Continue loop if current bar is still running.
            # if not (server_now.minute % self.timeframe == 0 and server_now.second == 1):
            #     continue

            # # Add the current bar to the trade bars data since it has already closed.
            # current_bars = trade.append_bars()
            # current_order_type = trade.get_order_type()
            # if current_order_type is None:
            #     continue

            # # strategy = Strategy(current_bars, current_order_type)
            # # confidence = strategy.confidence_rate()
    except KeyboardInterrupt:
        time.sleep(0.2)
        print(with_tag(f'Terminating "{p.name}" process (PID:{p.pid})...', "AWAIT"), end="\r", flush=True)
        time.sleep(1)
        clear_and_print(
            with_tag(
                f'"{p.name}" process (PID:{p.pid}) terminated.',
                "OK",
            )
        )
    except Exception as e:
        raise e
