import logging

from app.adapters.mt5_client import MT5Client
from app.config.settings import Settings
from app.infra.clock import JAKARTA_TZ, SessionWindow
from app.infra.logging import setup_logging
from app.infra.terminal import clear_terminal
from app.services.candle_monitor import CandleMonitorService
from app.services.scheduler import SchedulerService

logger = logging.getLogger(__name__)


def run() -> None:
    # Clear terminal
    clear_terminal()

    # Load settings
    settings = Settings()  # type: ignore

    # Configure logging
    setup_logging(settings.log_level)
    logger.info("Bootstrapping bot...")

    try:
        # Initialize MT5
        mt5 = MT5Client(settings.account_user, settings.account_pass, settings.server_id, settings.terminal_path)
        mt5.initialize()

        # Ensure timeframe support
        mt5.ensure_timeframe(settings.timeframe)

        # Ensure symbol selected
        # TODO Implement feature to process multi symbols
        mt5.ensure_symbol_selected(settings.symbol)
        meta = mt5.get_symbol_meta(settings.symbol)
        logger.info(
            f"Symbol ready: {meta.name} (digits={meta.digits}, tick_size={meta.tick_size:.{meta.digits}f}, tick_value={meta.tick_value}, lot_step={meta.lot_step}, min_lot={meta.min_lot}, stops_level={meta.stops_level}, freeze_level={meta.freeze_level})"
        )

        # Nudge the terminal to hydrate history faster at session open
        mt5.prime_history(settings.symbol, count=1500)

        # Enable candle monitoring service
        monitor = CandleMonitorService(
            mt5,
            settings.symbol,
            bootstrap_mode=True,  # log small warmup
            bootstrap_bars=10,
        )

        # Enable session-aware scheduler service
        window = SessionWindow(
            start_hour=settings.session_start_hour, end_hour=settings.session_end_hour, tz=JAKARTA_TZ
        )
        scheduler = SchedulerService(window=window, timeframe=mt5.timeframe, buffer_seconds=1.0)

        # Callback for scheduler.
        def on_candle_close():
            # Called once after each TF close within the session window.
            monitor.process_once()

        logger.info("Bootstrap complete.")

        # Run forever, scheduler will automatically handle sleep/session timing
        logger.info(
            "Starting scheduler: active Mon to Fri %02d:00 to %02d:00 (%s)",
            window.start_hour,
            window.end_hour,
            window.tz.key,
        )
        scheduler.run_forever(on_candle_close)

    except Exception as e:
        logger.exception(f"Fatal during bootstrap: {e}")
        # Trigger atexit by raising the error to the process, it will automatically shutdown MT5
        # to prevent a deadlock
        raise
