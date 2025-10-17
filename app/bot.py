import os
import time

import mt5_wrapper as mt5
from dotenv import load_dotenv

load_dotenv()

# Centralized configuration
RATE_POLLING_SEC = int(os.getenv("MT5_RATE_POLLING_SEC") or "60")
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH")
ACCOUNT_USER = int(os.getenv("MT5_ACCOUNT_USER") or "0")
ACCOUNT_PASS = os.getenv("MT5_ACCOUNT_PASS")
SERVER_URL = os.getenv("MT5_SERVER_URL")
SYMBOL = os.getenv("SYMBOL")


def healthcheck() -> str:
    """Returns a simple greeting."""
    return "Bot is healthy!"


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
    print("Initializing MT5 connection...")
    time.sleep(1)

    # Initialize MT5 with env-configured path, credentials, and server (5s timeout, non-portable),
    # raise if initialization fails.
    is_connected = mt5.initialize(
        path=MT5_TERMINAL_PATH,
        login=ACCOUNT_USER,
        password=ACCOUNT_PASS,
        server=SERVER_URL,
        timeout=5_000,
        portable=False,
    )
    if not is_connected:
        raise RuntimeError(f"MT5 initialization failed. Reason: {mt5.last_error()}.")

    # Retrieve terminal info, raise if retrieval fails
    if (terminal_info := mt5.terminal_info()) is None:
        raise RuntimeError(f"Unable to retrieve MT5 terminal information. Reason: {mt5.last_error()}.")

    print(f"[OK] Connected to MT5. Terminal={terminal_info.name}, Version={mt5.version()}.")

    # Select and validate the active trading symbol from environment, fail fast if missing or
    # selection fails.
    if not SYMBOL:
        raise RuntimeError("Active trading symbol is not set (env 'SYMBOL').")
    if not mt5.symbol_select(SYMBOL, True):
        raise RuntimeError(f"Failed to select symbol '{SYMBOL}'. Reason: {mt5.last_error()}.")

    print(f"[OK] Using {SYMBOL} as the active symbol.")

    # Fetch and report account authorization
    if (account_info_dict := mt5.account_info()) is None:
        raise RuntimeError(f"[Error] Unable to fetch account information. Reason: {mt5.last_error()}.")

    print(f"[OK] User authorized: Login={account_info_dict.login}, Server={account_info_dict.server}.")


def shutdown_mt5():
    """Shut down the MT5 session, safely ignoring any errors."""
    print("Shutting down...")
    try:
        mt5.shutdown()
    except Exception:
        pass


def run() -> None:
    """Main function for the bot."""
    clear_terminal()
    print(healthcheck())
    init_mt5()

    try:
        while True:
            time.sleep(RATE_POLLING_SEC)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_mt5()
