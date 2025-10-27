import logging

from app.adapters.mt5_client import MT5Client
from app.config.settings import Settings
from app.infra.logging import setup_logging
from app.infra.terminal import clear_terminal

logger = logging.getLogger(__name__)


def run() -> None:
    # Clear terminal
    clear_terminal()

    # Load settings
    settings = Settings()  # type: ignore

    # Configure logging
    setup_logging(settings.log_level)
    logger.info("Bootstrapping bot...")

    mt5 = MT5Client(settings.account_user, settings.account_pass, settings.server_id, settings.terminal_path)
    try:
        mt5.initialize()
        mt5.ensure_symbol_selected(settings.symbol)
        meta = mt5.get_symbol_meta(settings.symbol)
        logger.info(
            f"Symbol ready: {meta.name} (digits={meta.digits}, tick_size={meta.tick_size:.{meta.digits}f}, tick_value={meta.tick_value}, lot_step={meta.lot_step}, min_lot={meta.min_lot}, stops_level={meta.stops_level}, freeze_level={meta.freeze_level})"
        )
        logger.info("Bootstrap complete.")

    except Exception as e:
        logger.exception(f"Fatal during bootstrap: {e}")
        # Trigger atexit by raising the error to the process, it will automatically shutdown MT5
        # to prevent a deadlock
        raise
