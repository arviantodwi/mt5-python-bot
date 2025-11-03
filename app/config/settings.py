from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load environment variables and apply default metadata
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="forbid", frozen=True)

    # MetaTrader 5 terminal settings
    terminal_path: str = Field(
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        description="Path to the MetaTrader 5 terminal executable file. Optional. Default is C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    )

    # MetaTrader 5 account settings
    account_user: int = Field(..., description="User's login ID for account authentication. Required.")

    account_pass: str = Field(..., description="User's password for account authentication. Required.")

    server_id: str = Field(
        ..., description="Trading server to connect to when logging into the user's account. Required."
    )

    # Trade settings
    rr: float = Field(1.5, description="Multiplier for the risk-to-reward ratio. Optional. Default: 1.5.")

    risk_percentage: float = Field(
        0.01,
        description="Percentage of risk per trade (e.g., 0.01 for 1%). Optional. Default: 0.01.",
    )

    lot_step: float = Field(
        0.01,
        description="Step size for lot increment or decrement. Optional. Default: 0.01.",
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

    # Bot settings
    rate_polling_sec: int = Field(
        1, description="Time interval in seconds to poll for market rates. Optional. Default: 1."
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level to show in file and console. Optional. Default: INFO"
    )

    hydrate_max_retries: int = 3
    hydrate_retry_sec: float = 1.0
