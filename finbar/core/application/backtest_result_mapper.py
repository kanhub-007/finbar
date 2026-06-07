"""Map raw backtest engine dictionaries to BacktestResultDTO."""

from finbar.core.application.dto.backtest_result import BacktestResultDTO


def result_dto_from_raw(raw_result: dict) -> BacktestResultDTO:
    """Build a BacktestResultDTO from engine output."""
    return BacktestResultDTO(
        strategy_name=raw_result.get("strategy_name", ""),
        symbol=raw_result.get("symbol", ""),
        interval=raw_result.get("interval", ""),
        start_date=raw_result.get("start_date", ""),
        end_date=raw_result.get("end_date", ""),
        bar_count=raw_result.get("bar_count", 0),
        initial_cash=raw_result.get("initial_cash", 0.0),
        final_value=raw_result.get("final_value", 0.0),
        total_return=raw_result.get("total_return", 0.0),
        annualized_return=raw_result.get("annualized_return"),
        annualization_factor=raw_result.get("annualization_factor", 252.0),
        annualization_warning=raw_result.get("annualization_warning", ""),
        total_trades=raw_result.get("total_trades", 0),
        winning_trades=raw_result.get("winning_trades", 0),
        losing_trades=raw_result.get("losing_trades", 0),
        win_rate=raw_result.get("win_rate", 0.0),
        max_drawdown=raw_result.get("max_drawdown", 0.0),
        sharpe_ratio=raw_result.get("sharpe_ratio", 0.0),
        sortino_ratio=raw_result.get("sortino_ratio", 0.0),
        profit_factor=raw_result.get("profit_factor", 0.0),
        calmar_ratio=raw_result.get("calmar_ratio", 0.0),
        position_sizing=raw_result.get("position_sizing", ""),
        warmup_bars=raw_result.get("warmup_bars", 0),
        first_tradable=raw_result.get("first_tradable", ""),
        total_commission=raw_result.get("total_commission", 0.0),
        total_fees=raw_result.get("total_fees", 0.0),
        total_slippage=raw_result.get("total_slippage", 0.0),
        realized_pnl=raw_result.get("realized_pnl", 0.0),
        cash=raw_result.get("cash", 0.0),
        ending_position_size=raw_result.get("ending_position_size", 0.0),
        reconciliation_error=raw_result.get("reconciliation_error", 0.0),
        commission_pct=raw_result.get("commission_pct", 0.0),
        slippage_pct=raw_result.get("slippage_pct", 0.0),
        trades=raw_result.get("trades", []),
        equity_curve=raw_result.get("equity_curve", []),
        trust_diagnostics=raw_result.get("trust_diagnostics", {}),
        diagnostics=raw_result.get("diagnostics", []),
        error=raw_result.get("error"),
    )
