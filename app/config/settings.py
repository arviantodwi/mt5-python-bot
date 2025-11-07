from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load environment variables and apply default metadata
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="forbid", frozen=True)

    # ------------------------------------------------------------------------------
    #                        MetaTrader 5 Terminal Settings
    # ------------------------------------------------------------------------------
    terminal_path: str = Field(
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        description="Path to the MetaTrader 5 terminal executable file. Optional. Default is C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    )

    # ------------------------------------------------------------------------------
    #                         MetaTrader 5 Account Settings
    # ------------------------------------------------------------------------------
    account_user: int = Field(..., description="User's login ID for account authentication. Required.")

    account_pass: str = Field(..., description="User's password for account authentication. Required.")

    server_id: str = Field(
        ..., description="Trading server to connect to when logging into the user's account. Required."
    )

    # ------------------------------------------------------------------------------
    #                                Trade Settings
    # ------------------------------------------------------------------------------
    rr: float = Field(1.5, description="Multiplier for the risk-to-reward ratio. Optional. Default: 1.5.")

    risk_percentage: float = Field(
        0.01,
        description="Percentage of risk per trade (e.g., 0.01 for 1%). Optional. Default: 0.01.",
    )

    symbol: str = Field(..., description="Trading symbol to watch by bot. Required.")

    timeframe: int = Field(5, description="Candlestick timeframe in minutes. Optional. Default: 5.")

    session_start_hour: int = Field(
        7, description="Session window start in local time (24 hour). Optional. Default: 7."
    )

    session_end_hour: int = Field(
        3, description="Session window end in local time (24 hour). Can be overnight. Optional. Default: 3."
    )

    doji_ratio: float = Field(
        0.1,
        description="Ratio defining what constitutes a Doji candle. Optional. Default: 0.1.",
    )

    freeze_hours: Optional[float] = Field(
        None,
        description="Freeze window (in hours) that starts after a position is closed. Prevents new trades until the freeze period ends. Optional. Default: None.",
    )

    # Supported values:
    #   "off"          -> never adjust SL; skip trade if too close.
    #   "conservative" -> adjust SL only if required widening ≤ SL_NUDGE_FACTOR * planned distance.
    #   "flexible"     -> always adjust SL as needed.
    sl_nudge_mode: Literal["off", "conservative", "flexible"] = Field(
        "conservative",
        description="Stop-loss nudge policy to satisfy broker minimum stop distance (stops level). Optional. Default: conservative.",
    )

    sl_nudge_factor: float = Field(
        1.5,
        description='Maximum allowed widening multiplier for conservative nudge mode. Ignored if SL_NUDGE_MODE="off" or "flexible". Optional. Default: 1.5.',
    )

    enable_breakeven_sl: bool = Field(
        False,
        description="Enable automatic move of stop-loss to break-even once price reaches 1-Reward level. Optional. Default: False.",
    )

    # Supported values:
    # "close" -> move SL to break-even when the candle close reaches or exceeds +1R (more conservative).
    # "hl"    -> move SL to break-even when the candle's extreme (high/low) first touches +1R (earlier trigger).
    be_trigger_price: Literal["close", "hl"] = Field(
        "close",
        description="Break-even trigger price reference used when `ENABLE_BREAKEVEN_SL` is enabled. Optional. Default: close.",
    )
    """Break-even trigger price reference used when `ENABLE_BREAKEVEN_SL` is enabled. Optional. Default: close."""

    commission_per_lot: float = Field(
        0.0, description="Commission charged by the broker per 1.00 lot, in account currency. Optional. Default: 0.0."
    )

    # Supported values:
    # "fixed"  -> place a static take-profit at the RR-based distance; no trailing.
    # "trail"  -> do not place a hard TP; trail profits with a dynamic level and close when hit.
    # "hybrid" -> start with a fixed TP, then switch to trailing after price moves favorably.
    take_profit_mode: Literal["fixed", "trail", "hybrid"] = Field(
        "fixed", description="Take-profit management policy. Optional. Default: fixed."
    )

    atr_sl_multiplier: float = 2.5
    """ATR multiplier for initial SL"""

    atr_trail_multiplier: float = 0.8
    """ATR multiplier for trailing SL"""

    # ------------------------------------------------------------------------------
    #                                 Bot Settings
    # ------------------------------------------------------------------------------
    bot_name: str = Field(
        "BOTPYMT5",
        description="Bot name, used by MT5 terminal for the comment field in order request. Optional. Default: BOTPYMT5.",
    )
    """Bot name, used by MT5 terminal for the comment field in order request. Optional. Default: BOTPYMT5."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level to show in file and console. Optional. Default: INFO"
    )

    hydrate_max_retries: int = 3
    hydrate_retry_sec: float = 1.0
