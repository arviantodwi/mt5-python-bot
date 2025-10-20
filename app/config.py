import os
from typing import cast

from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Centralized configuration loaded from environment variables.

    Values are read once at import time. If a `.env` file is present,
    python-dotenv loads it so these settings can be provided without
    exporting environment variables manually.
    """

    # Seconds between market rate polls (default: 1).
    RATE_POLLING_SEC = int(os.getenv("MT5_RATE_POLLING_SEC") or "1")

    # Absolute path to the MetaTrader 5 terminal executable.
    MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH")

    # Numeric login/account ID (default: 0 = unset).
    ACCOUNT_USER = int(os.getenv("MT5_ACCOUNT_USER") or "0")

    # Password for the trading account.
    ACCOUNT_PASS = os.getenv("MT5_ACCOUNT_PASS")

    # Broker server address or name
    SERVER_URL = os.getenv("MT5_SERVER_URL")

    # Default trading symbol (e.g., "EURUSD")
    SYMBOL = os.getenv("SYMBOL")

    # Minimum lot size for orders
    MIN_LOT = 0.01
