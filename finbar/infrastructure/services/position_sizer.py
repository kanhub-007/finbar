"""PositionSizer — risk-based and explicit position sizing with affordability caps."""

from __future__ import annotations

from finbar.core.domain.entities.backtest_diagnostic import BacktestDiagnostic
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.leverage_config import LeverageConfig
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState

_DEFAULT_POSITION_SIZE = 100.0


class PositionSizer:
    """Compute position size and enforce buying-power affordability."""

    def __init__(self, config: ExecutionConfig) -> None:
        """Create a sizer bound to one execution configuration."""
        self._config = config
        self._leverage = LeverageConfig(multiplier=config.leverage_multiplier)

    def resolve(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        entry_price: float,
        portfolio_value: float,
    ) -> float:
        """Compute size and apply affordability cap. Returns filled size."""
        size = self._raw_size(entry, portfolio_value, entry_price)
        if size <= 0:
            return 0.0
        return self._apply_affordability_cap(state, entry, size, entry_price)

    # -- Raw sizing --------------------------------------------------------

    def _raw_size(
        self,
        entry: PendingEntry,
        portfolio_value: float,
        entry_price: float,
    ) -> float:
        """Compute position size before the affordability cap."""
        if entry.explicit_size and entry.position_size > 0:
            return float(entry.position_size)
        if entry.stop_price > 0:
            risk_amount = (
                portfolio_value
                * entry.risk_per_trade
                * self._config.risk_budget_multiplier()
            )
            risk_per_share = abs(entry_price - entry.stop_price)
            if risk_per_share > 0.001:
                return risk_amount / risk_per_share
        return _DEFAULT_POSITION_SIZE

    # -- Affordability cap -------------------------------------------------

    def _apply_affordability_cap(
        self,
        state: BacktestLoopState,
        entry: PendingEntry,
        size: float,
        price: float,
    ) -> float:
        """Cap position size to available margin / buying power."""
        if price <= 0 or self._config.allow_negative_cash:
            return size
        cap = self._max_affordable_size(state.cash, price)
        if cap <= 0:
            self._add_diagnostic(
                state,
                "order_rejected",
                "insufficient_cash",
                "Entry skipped because no buying power was available.",
            )
            return 0.0
        capped = min(size, cap)
        if capped >= size:
            return capped
        if entry.explicit_size and self._reject_oversized():
            self._add_diagnostic(
                state,
                "order_rejected",
                "explicit_size_rejected",
                (f"Explicit size {size:.8f} exceeds max " f"affordable {cap:.8f}."),
                {
                    "requested_size": size,
                    "max_affordable_size": cap,
                },
            )
            return 0.0
        self._add_diagnostic(
            state,
            "order_resized",
            "affordability_cap",
            f"Requested size {size:.8f} capped to {capped:.8f}.",
            {"requested_size": size, "filled_size": capped},
        )
        return capped

    def _max_affordable_size(self, cash: float, fill_price: float) -> float:
        """Maximum position size given equity, leverage, and entry cost."""
        if fill_price <= 0:
            return 0.0
        effective_price = fill_price * (1.0 + max(self._config.commission_pct, 0.0))
        if effective_price <= 0:
            return 0.0
        buying_power = cash * self._leverage.multiplier
        return max(0.0, buying_power / effective_price)

    def _reject_oversized(self) -> bool:
        return (
            self._config.reject_oversized_explicit_orders
            or not self._config.cap_explicit_size
        )

    @staticmethod
    def _add_diagnostic(
        state: BacktestLoopState,
        severity: str,
        code: str,
        message: str,
        extra: dict | None = None,
    ) -> None:
        state.diagnostics.append(
            BacktestDiagnostic(
                severity=severity,
                code=code,
                message=message,
                metadata=extra or {},
            )
        )
