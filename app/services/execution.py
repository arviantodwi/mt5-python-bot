from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.adapters.mt5_client import MT5Client
from app.domain.models import SymbolMeta
from app.domain.orders import OrderPlan, OrderResult, Side
from app.services.risk import RiskService

_l = logging.getLogger(__name__)
exec_logger = logging.LoggerAdapter(_l, extra={"tag": "Execution"})


@dataclass
class ExecutionService:
    """
    Orchestrates preflight checks, lot sizing, SL nudge policy, and market order sending via MT5Client.
    """

    mt5: MT5Client
    risk: RiskService
    nudge_mode: str  # "off" | "conservative" | "flexible"
    nudge_factor: float

    def execute_market(self, plan: OrderPlan) -> Optional[OrderResult]:
        """
        Execute a market order based on an OrderPlan and live broker state.
        Returns None if preflight or validations fail and we skip the trade.
        """
        symbol = plan.symbol
        meta = self.mt5.get_symbol_meta(symbol)
        if meta is None:
            exec_logger.warning("Symbol meta not available for %s; skipping order.", symbol)
            return None

        price_format = f"%.{meta.digits}f"
        exec_logger.debug(
            "Received OrderPlan: symbol=%s, side=%s, rr=%.2f, planned_sl=%f",
            plan.symbol,
            plan.side.value,
            plan.rr,
            price_format % plan.planned_sl,
        )

        # Account & quote
        balance = self.mt5.get_account_balance()
        quote = self.mt5.get_quote(symbol)
        if quote is None:
            exec_logger.warning("No live quote for %s; skipping order.", symbol)
            return None

        entry = quote.ask if plan.side == Side.BUY else quote.bid

        # Apply SL nudge policy using broker stops_level (points)
        sl = self._apply_sl_nudge(
            policy=self.nudge_mode,
            factor=self.nudge_factor,
            planned_sl=plan.planned_sl,
            entry=entry,
            side=plan.side,
            meta=meta,
        )
        if sl is None:
            exec_logger.info("SL nudge policy rejected the trade for %s.", symbol)
            return None

        # Recompute TP to preserve RR
        tp = self._compute_tp(entry=entry, sl=sl, rr=plan.rr, side=plan.side)
        sl = self._round_to_digits(sl, meta.digits)
        tp = self._round_to_digits(tp, meta.digits)

        # Compute lot based on risk and actual SL distance
        lot, risk_used = self.risk.compute_lot(balance=balance, entry_price=entry, stop_loss=sl, meta=meta)
        if lot <= 0.0:
            exec_logger.info("Lot computed as 0 for %s; risk or distances invalid; skipping.", symbol)
            return None

        # Send order
        try:
            send_res = self.mt5.send_market_order(symbol=symbol, side=plan.side, volume=lot, sl=sl, tp=tp)
        except Exception as exc:
            exec_logger.exception("Order send failed for %s: %s", symbol, exc)
            return None

        if send_res is None or send_res.status != "FILLED":
            reason = getattr(send_res, "reason", "UNKNOWN")
            exec_logger.info("Order rejected for %s: %s", symbol, reason)
            return None

        exec_logger.info(
            "%s order filled for %s (lot=%s, entry=%f, SL=%f, TP=%f, ticket=%s)",
            plan.side.value,
            symbol,
            lot,
            price_format % send_res.entry_price,
            price_format % send_res.stop_loss,
            price_format % send_res.take_profit,
            send_res.ticket,
        )

        # Map adapter result → domain result
        return OrderResult(
            symbol=symbol,
            side=plan.side,
            lot=lot,
            entry_price=send_res.entry_price,
            stop_loss=send_res.stop_loss,  # or use `sl` (already rounded) if prefered
            take_profit=send_res.take_profit,  # or `tp`
            ticket=send_res.ticket,
            time_utc=send_res.time_utc,
            status="FILLED",
            reason=send_res.reason,
        )

    def _apply_sl_nudge(
        self,
        policy: str,
        factor: float,
        planned_sl: float,
        entry: float,
        side: Side,
        meta: SymbolMeta,
    ) -> Optional[float]:
        """
        Validate/adjust SL against broker stops_level (points) and tick_size.
        Returns adjusted SL or None if policy forbids.
        """
        min_points = max(0, meta.stops_level)  # points
        min_price_dist = min_points * meta.tick_size
        dist = abs(entry - planned_sl)

        if dist >= min_price_dist - 1e-12:
            return planned_sl  # ok

        if policy == "off":
            return None

        required_factor = min_price_dist / max(dist, 1e-12)
        if policy == "conservative" and required_factor > max(1.0, factor):
            return None

        # apply nudge
        if side == Side.BUY:
            return entry - min_price_dist
        else:
            return entry + min_price_dist

    @staticmethod
    def _compute_tp(entry: float, sl: float, rr: float, side: Side) -> float:
        risk = abs(entry - sl)
        if side == Side.BUY:
            return entry + rr * risk
        else:
            return entry - rr * risk

    @staticmethod
    def _round_to_digits(price: float, digits: int) -> float:
        """Round price to the given number of symbol digits."""
        return price if digits < 0 else round(price, digits)
