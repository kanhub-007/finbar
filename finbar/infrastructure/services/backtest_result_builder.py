"""BacktestResultBuilder — compute metrics and assemble the result dict.

Pure transformation from BacktestLoopState + metadata to the engine's
output dict. One class with a single public build() method.
"""

from __future__ import annotations

from finbar.core.domain.entities.backtest_diagnostic import BacktestDiagnostic
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.core.domain.services.annualization import (
    annualization_factor as _annualization_factor,
)
from finbar.core.domain.services.backtest_metrics import (
    calculate_annualised_return,
    calculate_calmar_ratio,
    calculate_daily_returns,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe,
    calculate_sortino,
    calculate_total_return,
)
from finbar.core.domain.services.rolling_metrics import (
    calculate_exposure,
    calculate_monthly_returns,
    calculate_rolling_drawdown,
    calculate_rolling_pnl,
    calculate_rolling_sharpe,
    calculate_rolling_win_rate,
    calculate_trade_distribution,
    calculate_yearly_returns,
)
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState


class BacktestResultBuilder:
    """Compute performance metrics and assemble the engine output dict."""

    def build(
        self,
        strategy: TradingStrategy,
        state: BacktestLoopState,
        initial_cash: float,
        interval: str = "",
        warmup_bars: int = 0,
        first_tradable: str = "",
        execution_config: ExecutionConfig | None = None,
    ) -> dict:
        """Compute metrics and assemble the backtest result dict."""
        config = execution_config or ExecutionConfig()
        metrics = self._compute_metrics(state, initial_cash, config, interval)
        reconciliation = self._compute_reconciliation(state, initial_cash)
        trust = self._build_trust_diagnostics(
            config,
            warmup_bars,
            first_tradable,
            metrics["annualization_factor"],
            metrics["annualization_warning"],
            state,
        )
        meta = strategy.meta()
        dates = [e["date"] for e in state.equity_curve]

        analytics = self._compute_analytics(
            state, metrics["annualization_factor"], metrics.get("total_trades", 0)
        )

        return {
            "strategy_name": meta.name,
            "symbol": "",
            "interval": "",
            "start_date": dates[0] if dates else "",
            "end_date": dates[-1] if dates else "",
            "bar_count": len(state.equity_curve),
            "initial_cash": initial_cash,
            "position_sizing": "risk-based-v3-fill-price",
            "warmup_bars": warmup_bars,
            "first_tradable": first_tradable,
            "commission_pct": round(config.commission_pct, 6),
            "slippage_pct": round(config.slippage_pct, 6),
            "trades": state.trades,
            "equity_curve": state.equity_curve,
            **metrics,
            **reconciliation,
            "analytics": analytics,
            "trust_diagnostics": trust,
            "diagnostics": _diagnostics_to_dicts(state.diagnostics),
        }

    @staticmethod
    def _compute_metrics(
        state: BacktestLoopState,
        initial_cash: float,
        config: ExecutionConfig,
        interval: str,
    ) -> dict:
        """Compute performance metrics from equity curve and trades."""
        equity_values = [e["value"] for e in state.equity_curve]
        final_value = equity_values[-1] if equity_values else initial_cash
        ann_factor, ann_warning = _annualization_factor(
            interval, config.market_calendar
        )

        daily_returns = (
            calculate_daily_returns(equity_values) if len(equity_values) > 1 else []
        )
        total_return = calculate_total_return(initial_cash, final_value)
        max_dd = calculate_max_drawdown(equity_values) if equity_values else 0.0
        sharpe = (
            calculate_sharpe(daily_returns, annualization_factor=ann_factor)
            if daily_returns
            else 0.0
        )
        sortino = (
            calculate_sortino(daily_returns, annualization_factor=ann_factor)
            if daily_returns
            else 0.0
        )

        gross_profit = sum(t["pnl"] for t in state.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in state.trades if t["pnl"] <= 0))
        profit_factor = calculate_profit_factor(gross_profit, gross_loss)

        trading_days = len(state.equity_curve)
        annualised_return = calculate_annualised_return(
            total_return,
            trading_days,
            annualization_factor=ann_factor,
        )
        calmar = calculate_calmar_ratio(annualised_return, max_dd)

        winning = sum(1 for t in state.trades if t["pnl"] > 0)
        losing = sum(1 for t in state.trades if t["pnl"] <= 0)
        total_trades = len(state.trades)
        win_rate = winning / total_trades if total_trades > 0 else 0.0

        return {
            "final_value": round(final_value, 2),
            "total_return": round(total_return, 4),
            "annualized_return": round(annualised_return, 4),
            "annualization_factor": ann_factor,
            "annualization_warning": ann_warning,
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round(win_rate, 4),
            "max_drawdown": round(max_dd, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "profit_factor": (
                round(profit_factor, 4) if profit_factor != float("inf") else None
            ),
            "calmar_ratio": round(calmar, 4),
        }

    @staticmethod
    def _compute_reconciliation(
        state: BacktestLoopState,
        initial_cash: float,
    ) -> dict:
        """Compute accounting reconciliation fields."""
        equity_values = [e["value"] for e in state.equity_curve]
        final_value = equity_values[-1] if equity_values else initial_cash
        realized_pnl = sum(t["pnl"] for t in state.trades)
        return {
            "total_commission": round(state.total_commission, 2),
            "total_borrow_cost": round(state.total_borrow_cost, 2),
            "total_fees": round(state.total_commission, 2),
            "total_slippage": round(state.total_slippage, 2),
            "realized_pnl": round(realized_pnl, 2),
            "cash": round(state.cash, 2),
            "ending_position_size": state.position.size,
            "reconciliation_error": round(final_value - initial_cash - realized_pnl, 2),
        }

    @staticmethod
    def _build_trust_diagnostics(
        config: ExecutionConfig,
        warmup_bars: int,
        first_tradable: str,
        annualization_factor: float,
        annualization_warning: str,
        state: BacktestLoopState,
    ) -> dict:
        """Assemble the trust diagnostics block."""
        return {
            "gap_aware_fills": True,
            "lookahead_safe_mtf": True,
            "liquidated_on_close": True,
            "net_trade_metrics": True,
            "entry_slippage_accounted": True,
            "entry_model": "next_bar_open",
            "exit_model": "next_bar_open",
            "cost_model": (
                "commission_and_slippage"
                if config.commission_pct > 0 or config.slippage_pct > 0
                else "zero_cost"
            ),
            "warmup_bars": warmup_bars,
            "first_tradable": first_tradable,
            "commission_pct": round(config.commission_pct, 6),
            "slippage_pct": round(config.slippage_pct, 6),
            "risk_mode": config.risk_mode,
            "leverage": config.leverage_multiplier,
            "cap_explicit_size": config.cap_explicit_size,
            "reject_oversized_explicit_orders": (
                config.reject_oversized_explicit_orders
            ),
            "allow_negative_cash": config.allow_negative_cash,
            "borrow_fee_annual_pct": config.borrow_fee_annual_pct,
            "margin_mode": config.margin_mode,
            "market_calendar": config.market_calendar,
            "annualization_factor": annualization_factor,
            "annualization_warning": annualization_warning,
            "diagnostics": _diagnostics_to_dicts(state.diagnostics),
        }

    @staticmethod
    def _compute_analytics(
        state: BacktestLoopState,
        periods_per_year: float,
        total_trades: int,
    ) -> dict:
        """Compute rolling and distribution analytics."""
        equity_values = [e["value"] for e in state.equity_curve]
        if not equity_values:
            return _ANALYTICS_EMPTY

        return {
            "rolling_sharpe_60": calculate_rolling_sharpe(
                equity_values, window=60, periods_per_year=periods_per_year
            ),
            "rolling_win_rate_60": calculate_rolling_win_rate(
                state.trades, state.equity_curve, window=60
            ),
            "rolling_drawdown": calculate_rolling_drawdown(equity_values),
            "rolling_pnl_60": calculate_rolling_pnl(equity_values, window=60),
            "monthly_returns": calculate_monthly_returns(state.equity_curve),
            "yearly_returns": calculate_yearly_returns(state.equity_curve),
            "exposure": calculate_exposure(state.equity_curve),
            "trade_distribution": (
                calculate_trade_distribution(state.trades)
                if total_trades > 0
                else calculate_trade_distribution([])
            ),
        }


_ANALYTICS_EMPTY: dict = {
    "rolling_sharpe_60": [],
    "rolling_win_rate_60": [],
    "rolling_drawdown": [],
    "rolling_pnl_60": [],
    "monthly_returns": {},
    "yearly_returns": {},
    "exposure": [],
    "trade_distribution": {
        "pnl_bins": [],
        "pnl_counts": [],
        "pnl_percentiles": {},
        "duration_bins": [],
        "duration_counts": [],
        "duration_percentiles": {},
        "avg_pnl": 0.0,
        "avg_duration": 0.0,
    },
}


def _diagnostics_to_dicts(items: list[BacktestDiagnostic]) -> list[dict]:
    """Return JSON-serializable diagnostic dictionaries."""
    return [item.to_dict() for item in items]
