"""BacktestResultBuilder — compute metrics and assemble the result dict.

Pure transformation from BacktestLoopState + metadata to the engine's
output dict. No side effects, no pandas, no framework dependencies.
"""

from __future__ import annotations

from finbar.core.domain.entities.backtest_diagnostic import BacktestDiagnostic
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
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
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState


def build_result(
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
    equity_values = [e["value"] for e in state.equity_curve]
    final_value = equity_values[-1] if equity_values else initial_cash
    annualization_factor, annualization_warning = _annualization_factor(interval)

    daily_returns = (
        calculate_daily_returns(equity_values) if len(equity_values) > 1 else []
    )
    total_return = calculate_total_return(initial_cash, final_value)
    max_dd = calculate_max_drawdown(equity_values) if equity_values else 0.0
    sharpe = (
        calculate_sharpe(daily_returns, annualization_factor=annualization_factor)
        if daily_returns
        else 0.0
    )
    sortino = (
        calculate_sortino(daily_returns, annualization_factor=annualization_factor)
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
        annualization_factor=annualization_factor,
    )
    calmar = calculate_calmar_ratio(annualised_return, max_dd)

    winning = sum(1 for t in state.trades if t["pnl"] > 0)
    losing = sum(1 for t in state.trades if t["pnl"] <= 0)
    total_trades = len(state.trades)
    win_rate = winning / total_trades if total_trades > 0 else 0.0

    realized_pnl = sum(t["pnl"] for t in state.trades)
    total_fees = state.total_commission
    ending_position_size = state.position.size
    reconciliation_error = round(final_value - initial_cash - realized_pnl, 2)

    meta = strategy.meta()
    dates = [e["date"] for e in state.equity_curve]
    start_date = dates[0] if dates else ""
    end_date = dates[-1] if dates else ""

    return {
        "strategy_name": meta.name,
        "symbol": "",
        "interval": "",
        "start_date": start_date,
        "end_date": end_date,
        "bar_count": len(state.equity_curve),
        "initial_cash": initial_cash,
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 4),
        "annualized_return": round(annualised_return, 4),
        "annualization_factor": annualization_factor,
        "position_sizing": "risk-based-v3-fill-price",
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
        "warmup_bars": warmup_bars,
        "first_tradable": first_tradable,
        "total_commission": round(state.total_commission, 2),
        "total_fees": round(total_fees, 2),
        "total_slippage": round(state.total_slippage, 2),
        "realized_pnl": round(realized_pnl, 2),
        "cash": round(state.cash, 2),
        "ending_position_size": ending_position_size,
        "reconciliation_error": reconciliation_error,
        "commission_pct": round(config.commission_pct, 6),
        "slippage_pct": round(config.slippage_pct, 6),
        "trades": state.trades,
        "equity_curve": state.equity_curve,
        "trust_diagnostics": {
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
            "market_calendar": config.market_calendar,
            "annualization_factor": annualization_factor,
            "annualization_warning": annualization_warning,
            "diagnostics": _diagnostics_to_dicts(state.diagnostics),
        },
        "diagnostics": _diagnostics_to_dicts(state.diagnostics),
    }


def _diagnostics_to_dicts(items: list[BacktestDiagnostic]) -> list[dict]:
    """Return JSON-serializable diagnostic dictionaries."""
    return [item.to_dict() for item in items]


def _annualization_factor(interval: str) -> tuple[float, str]:
    """Return approximate periods per year and warning for an interval."""
    normalized = interval.lower().strip()
    factors = {
        "1d": 252.0,
        "1w": 52.0,
        "1h": 252.0 * 6.5,
        "1m": 252.0 * 390.0,
        "5m": 252.0 * 78.0,
        "5min": 252.0 * 78.0,
        "15m": 252.0 * 26.0,
        "15min": 252.0 * 26.0,
        "30m": 252.0 * 13.0,
        "30min": 252.0 * 13.0,
        "4h": 252.0 * 1.625,
    }
    if normalized in factors:
        return factors[normalized], ""
    return 252.0, "Unknown interval; annualized metrics use 1d equity assumption."
