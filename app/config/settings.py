from decimal import Decimal
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load environment variables and apply default metadata
    model_config = SettingsConfigDict(env_file=".env", extra="forbid", frozen=True)

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
    rr: Decimal = Field(
        Decimal(1.5), decimal_places=1, description="Multiplier for the risk-to-reward ratio. Optional. Default: 1.5."
    )

    risk_percentage: Decimal = Field(
        Decimal(0.01),
        decimal_places=2,
        description="Percentage of risk per trade (e.g., 0.01 for 1%). Optional. Default: 0.01.",
    )

    lot_step: Decimal = Field(
        Decimal(0.01),
        decimal_places=2,
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

    # Bot settings
    rate_polling_sec: int = Field(
        1, description="Time interval in seconds to poll for market rates. Optional. Default: 1."
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level to show in file and console. Optional. Default: INFO"
    )
