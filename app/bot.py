import multiprocessing
import os
import sys
import time
from datetime import datetime, timezone
from typing import cast
from multiprocessing import Process

import mt5_wrapper as mt5

from .config import Config
from .helper import clear_and_print, colorize_text, parse_mt5_version, with_mt5_error, with_tag

# from .strategy import Strategy
from .trader import Trader

# from .trading import Trading
from .market import Market, market_watch_worker

# import numpy as np
# import pandas as pd
# import pandas_ta as ta
# from zoneinfo import ZoneInfo
# from talib import CDL3BLACKCROWS as ThreeBlackRows
# from talib import CDL3WHITESOLDIERS as ThreeWhiteSoldiers
# from talib import CDLENGULFING as Engulfing


def healthcheck() -> None:
    """Returns a simple greeting."""
    print("Bot is healthy!")


def clear_terminal():
    """Clear the terminal screen on Windows, Unix, and Linux."""
    if os.name == "nt":  # Windows
        _ = os.system("cls")
    else:  # Unix and Linux
        _ = os.system("clear")


def init_mt5():
    """Initialize and validate an MT5 session.

    Establishes a connection to MetaTrader 5 using environment-provided
    terminal path, account credentials, and server. Verifies terminal
    information, selects the active trading symbol, and confirms account
    authorization. Prints status updates to stdout.

    Raises:
        RuntimeError: If initialization, terminal info retrieval, symbol
            selection, or account info retrieval fails.
    """

    print(with_tag("Initializing MT5 connection..."), end="\r")
    time.sleep(1)

    is_mt5_connected = False

    try:
        # Initialize MT5 with env-configured path, credentials, and server (5s timeout, non-portable),
        # raise if initialization fails.
        if not mt5.initialize(Config.MT5_TERMINAL_PATH, portable=False):
            raise RuntimeError(with_mt5_error("MT5 initialization failed.", "FATAL"))

        # Retrieve terminal info, raise if retrieval fails
        if (terminal_info := mt5.terminal_info()) is None:
            raise RuntimeError(with_mt5_error("Unable to retrieve MT5 terminal information.", "FATAL"))

        clear_and_print(with_tag("MT5 connection initialized.", "OK"))
        print(with_tag(f"Connected to {terminal_info.name}. Terminal version is {parse_mt5_version(mt5.version())}."))

        is_mt5_connected = True

        # Select and validate the active trading symbol from environment, fail fast if missing or
        # selection fails.
        if not Config.SYMBOL:
            raise RuntimeError(with_tag("Active trading symbol is not set (env 'SYMBOL').", "FATAL"))
        if not mt5.symbol_select(Config.SYMBOL, True):
            raise RuntimeError(with_mt5_error(f"Failed to select symbol {colorize_text(Config.SYMBOL)}.", "FATAL"))

        print(with_tag(f"Using {colorize_text(Config.SYMBOL)} as the active symbol."))

        # Attempt to get current date and time from the selected symbol
        if (info := mt5.symbol_info(Config.SYMBOL)) is None:
            raise RuntimeError(with_mt5_error(f"Failed to retrieve {Config.SYMBOL} info tick.", "FATAL"))

        server_now = datetime.fromtimestamp(info.time, tz=timezone.utc)
        server_time = server_now.strftime("%B %d %Y, %H:%M:%S")

        print(with_tag(f"Inferring server date and time: {server_time}."))
    except RuntimeError as e:
        print(e)
        shutdown_mt5(show_message=is_mt5_connected)


def shutdown_mt5(show_message: bool = True):
    """Shut down the MT5 session, safely ignoring any errors."""

    if show_message:
        print(with_tag("Shutting down MT5...", "INFO"), end="\r")
        time.sleep(1)

        try:
            mt5.shutdown()
        except Exception:
            pass
        finally:
            clear_and_print(with_tag("MT5 shut down gracefully.", "OK"))
    else:
        mt5.shutdown()

    sys.exit()


def run() -> None:
    """Main function for the bot."""

    clear_terminal()
    healthcheck()
    init_mt5()

    market_process: Process | None = None

    try:
        # It’s safe to cast the symbol value since it has already been validated
        # during the MT5 initialization phase.
        symbol = cast(str, Config.SYMBOL)
        market = Market(symbol, timeframe=mt5.TIMEFRAME_M5, poll_interval=Config.RATE_POLLING_SEC)

        bot = Trader()
        # bot.set_ta()

        # trade = Trading(cast(str, Config.SYMBOL), mt5.TIMEFRAME_M5)

        # bot.watch_market(symbol, timeframe=mt5.TIMEFRAME_M5, poll_interval=Config.RATE_POLLING_SEC)

        parent_conn, child_conn = multiprocessing.Pipe()
        market_process = multiprocessing.Process(
            name=f"{symbol} Market Watch",
            target=market_watch_worker,
            args=(child_conn, symbol, market.timeframe, market.poll_interval),
            daemon=True,
        )
        market_process.start()
        print(
            with_tag(
                f"Starting to watch {colorize_text(symbol)} market rates. Press {colorize_text('Ctrl+C', 'WARN')} to stop."
            )
        )

        while market_process.is_alive():
            # print(f"message from market: {parent_conn.recv()}")
            # print("foobar")
            # tick = mt5.symbol_info_tick(symbol)
            # if tick is None:
            #     raise RuntimeError(f"Failed to retrieve {symbol} info tick.")

            # time_format = "%H:%M"
            # # if seconds:
            # #     time_format += "%S"
            # server_now = datetime.fromtimestamp(tick.time, tz=timezone.utc)
            # server_time = server_now.strftime(time_format)
            # print(server_time)
            time.sleep(0.25)

    except KeyboardInterrupt:
        if isinstance(market_process, Process):
            print(
                with_tag(
                    f'Ctrl+C detected. Initiating termination of "{market_process.name}" process (PID:{market_process.pid}).',
                    "WARN",
                )
            )
    except Exception as e:
        print(e)
    finally:
        if isinstance(market_process, Process):
            market_process.join()
        shutdown_mt5()
