import logging
from datetime import datetime, timezone

from app.adapters.mt5_client import MT5Client
from app.config.settings import Settings
from app.infra.clock import JAKARTA_TZ, SessionWindow
from app.infra.logging import setup_logging
from app.infra.terminal import clear_terminal
from app.infra.timeframe import timeframe_to_seconds
from app.services.candle_monitor import CandleMonitorService
from app.services.execution import ExecutionService
from app.services.indicators import IndicatorsService
from app.services.order_planner import OrderPlannerService
from app.services.position_guard import PositionGuardService
from app.services.risk import RiskService
from app.services.scheduler import SchedulerService
from app.services.signal import SignalService

logger = logging.getLogger(__name__)


def run() -> None:
    # Clear terminal
    clear_terminal()

    # Load settings
    settings = Settings.model_validate({})

    # Configure logging
    setup_logging(settings.log_level)
    logger.info("Bootstrapping bot...")

    try:
        # Initialize MT5
        mt5 = MT5Client(settings.account_user, settings.account_pass, settings.server_id, settings.terminal_path)
        mt5.initialize(settings.symbol, settings.timeframe, prime_count=1500)

        # Enable services
        # Indicators
        indicators = IndicatorsService(histogram_window=4)

        # Signals
        signals = SignalService(
            symbol=settings.symbol, timeframe_minutes=settings.timeframe, doji_ratio=settings.doji_ratio
        )

        # Risk Calculator
        risk = RiskService(risk_percentage=settings.risk_percentage)

        # Order Planner
        planner = OrderPlannerService(settings.rr)

        # Position Guard
        guard = PositionGuardService(mt5=mt5, risk=risk, symbol=settings.symbol, freeze_hours=settings.freeze_hours)

        # Execution
        executor = ExecutionService(
            mt5=mt5,
            risk=risk,
            nudge_mode=settings.sl_nudge_mode,
            nudge_factor=settings.sl_nudge_factor,
        )

        # Candle Monitoring
        monitor = CandleMonitorService(
            mt5=mt5,
            symbol=settings.symbol,
            bootstrap_mode=True,  # log small warmup
            bootstrap_bars=1,
            indicators=indicators,
            signals=signals,
            planner=planner,
            guard=guard,
            executor=executor,
        )

        # Scheduler
        window = SessionWindow(
            start_hour=settings.session_start_hour, end_hour=settings.session_end_hour, tz=JAKARTA_TZ
        )
        scheduler = SchedulerService(window=window, timeframe=mt5.timeframe, buffer_seconds=1.0)

        # Seed indicators pack with recent bars so EMA200 & MACD histogram are ready from the first live bar
        last = mt5.get_last_closed_candle(settings.symbol)
        if last:
            tf_sec = timeframe_to_seconds(mt5.timeframe)
            since = last.epoch - (1500 * tf_sec)
            warmup_candles = mt5.get_backfill_candles(
                symbol=settings.symbol,
                since_exclusive_epoch=since,
                until_inclusive_epoch=last.epoch,
            )
            if warmup_candles:
                indicators.warmup_with_candles(warmup_candles)
                logger.info(
                    "Indicators prewarmed with %d bars | last=%s, since=%s",
                    len(warmup_candles),
                    last.time_utc.strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.fromtimestamp(since + 1, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                )
            else:
                logger.warning("No warmup candles returned; indicators will warm live.")

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
