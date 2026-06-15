"""BacktestRunner — bar-by-bar backtest engine implementing BacktestEngine(ABC).

Template Method + Facade: the runner delegates to PositionExecutor for
position lifecycle and BacktestResultBuilder for metrics assembly.
"""

from __future__ import annotations

import logging

import pandas as pd
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy

from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.core.domain.entities.pending_exit import PendingExit
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.infrastructure.services.backtest_data_validator import (
    validate_backtest_frame,
)
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.backtest_result_builder import BacktestResultBuilder
from finbar.infrastructure.services.position_executor import PositionExecutor

logger = logging.getLogger(__name__)

_DEFAULT_RISK_PER_TRADE = 0.02


class BacktestRunner(BacktestEngine):
    """Bar-by-bar backtest runner for any bar interval.

    Supports long and short positions, conservative entry (next-bar open),
    gap-aware stop-loss and take-profit execution, and full equity tracking.

    Position sizing: if the strategy provides position_size in its signal,
    that value is used. Otherwise, the engine computes risk-based sizing at
    the actual entry fill price: size = (portfolio * risk_per_trade) / risk.
    Falls back to 100 shares if no valid stop is set.
    """

    def run(
        self,
        df: pd.DataFrame,
        strategy: TradingStrategy,
        initial_cash: float = 10000.0,
        **params,
    ) -> dict:
        """Execute a backtest and return structured results as a dict.

        Warmup bars (before ``first_tradable_index``) are fed to
        ``strategy.on_bar()`` so crossover and other stateful conditions can
        build their baseline, but no trades are executed or queued during
        warmup.
        """
        if df.empty:
            return _error_result("No bars provided")

        validation_error = validate_backtest_frame(df)
        if validation_error is not None:
            return _error_result(validation_error)

        strategy.on_reset()

        risk_per_trade = float(params.pop("risk_per_trade", _DEFAULT_RISK_PER_TRADE))
        interval = str(params.pop("interval", "") or "")
        warmup_bars = int(params.pop("warmup_bars", 0) or 0)
        first_tradable = str(params.pop("first_tradable", "") or "")
        commission_pct = float(params.pop("commission_pct", 0.0) or 0.0)
        slippage_pct = float(params.pop("slippage_pct", 0.0) or 0.0)
        execution_config = _execution_config_from_params(
            params,
            commission_pct,
            slippage_pct,
        )

        executor = PositionExecutor(execution_config)
        state = _run_loop(
            df, strategy, initial_cash, risk_per_trade, executor, warmup_bars
        )

        return BacktestResultBuilder().build(
            strategy,
            state,
            initial_cash,
            interval,
            warmup_bars,
            first_tradable,
            execution_config,
        )


def _execution_config_from_params(
    params: dict,
    commission_pct: float,
    slippage_pct: float,
) -> ExecutionConfig:
    """Build execution config from engine params."""
    return ExecutionConfig(
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        leverage_multiplier=float(params.pop("leverage", 1.0) or 1.0),
        risk_mode=str(
            params.pop("risk_mode", "fixed_equity_risk") or "fixed_equity_risk"
        ),
        cap_explicit_size=_bool_param(params.pop("cap_explicit_size", True)),
        reject_oversized_explicit_orders=_bool_param(
            params.pop("reject_oversized_explicit_orders", False)
        ),
        allow_negative_cash=_bool_param(params.pop("allow_negative_cash", False)),
        market_calendar=str(
            params.pop("market_calendar", "equity_regular_hours") or ""
        ),
        borrow_fee_annual_pct=float(params.pop("borrow_fee_annual_pct", 0.0) or 0.0),
        margin_mode=str(params.pop("margin_mode", "simplified") or "simplified"),
        maintenance_margin_pct=float(
            params.pop("maintenance_margin_pct", 0.005) or 0.005
        ),
        enable_funding=_bool_param(params.pop("enable_funding", False)),
        funding_rate=float(params.pop("funding_rate", 0.0001) or 0.0001),
        risk_price_basis=str(
            params.pop("risk_price_basis", "signal_close") or "signal_close"
        ),
        borrow_time_basis=str(
            params.pop("borrow_time_basis", "calendar_day") or "calendar_day"
        ),
    )


def _bool_param(value) -> bool:
    """Parse bool-like params from JSON/MCP payloads."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


# ---------------------------------------------------------------------------
# Bar loop
# ---------------------------------------------------------------------------


def _run_loop(
    df: pd.DataFrame,
    strategy: TradingStrategy,
    initial_cash: float,
    risk_per_trade: float,
    executor: PositionExecutor,
    first_tradable_index: int = 0,
) -> BacktestLoopState:
    """Iterate bars, call strategy, execute signals, track positions.

    Bars before ``first_tradable_index`` are warmup: ``strategy.on_bar()``
    is called so stateful conditions (crossovers) build their baseline, but
    no pending orders are executed and no new signals are queued.
    """
    state = BacktestLoopState(initial_cash)
    executor.setup_full_margin(initial_cash)
    final_close = 0.0
    final_date = ""

    # Pre-extract hot columns to numpy arrays. The per-bar dict is
    # built on-the-fly from numpy arrays rather than via df.to_dict("records")
    # which would duplicate all data (potentially hundreds of MB) in memory.
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    dates = _precompute_dates(df.index)
    # Pre-extract indicator/feature columns as numpy arrays for the bar dict.
    extra_cols = {
        col: df[col].to_numpy()
        for col in df.columns
        if col not in ("open", "high", "low", "close")
    }
    column_names = list(extra_cols.keys())
    n_bars = len(df)

    for i in range(n_bars):
        open_price = float(opens[i])
        high = float(highs[i])
        low = float(lows[i])
        close = float(closes[i])
        bar_date = dates[i]
        # Build bar dict on-the-fly — only one allocation per bar instead
        # of a full list of pre-built dicts.
        bar_dict = {"open": open_price, "high": high, "low": low, "close": close}
        for col_name in column_names:
            bar_dict[col_name] = extra_cols[col_name][i]
        final_close = close
        final_date = bar_date

        if i < first_tradable_index:
            _update_warmup_state(state, strategy, bar_dict)
            continue

        _execute_pending(state, open_price, bar_date, executor)
        executor.check_exit_conditions(state, open_price, high, low, bar_date)
        executor.check_margin_call(state, close)
        executor.apply_funding(state)
        _process_signal(
            state,
            strategy,
            bar_dict,
            open_price,
            close,
            bar_date,
            risk_per_trade,
        )
        _track_equity(state, close, bar_date, executor)
        executor.sync_margin_equity(state)

    executor.liquidate_open(state, final_close, final_date)
    _log_run_summary(state)
    return state


def _update_warmup_state(
    state: BacktestLoopState,
    strategy: TradingStrategy,
    bar: dict,
) -> None:
    """Feed a warmup bar to the strategy for state updates only.

    No trades are executed or queued. The position is always flat during
    warmup so the strategy receives an empty position dict.
    """
    strategy.on_bar(bar, state.position.to_dict())


def _execute_pending(
    state: BacktestLoopState,
    price: float,
    date: str,
    executor: PositionExecutor,
) -> None:
    """Execute pending exit/entry signals at next bar's open."""
    if state.pending_exit is not None and state.position.size != 0:
        executor.exit_position(state, price, date, exit_reason="signal_exit_next_open")
        state.pending_exit = None

    if state.pending_entry is None or state.position.size != 0:
        return
    entry = state.pending_entry
    state.pending_entry = None
    executor.enter(state, entry, price, date)


def _process_signal(
    state: BacktestLoopState,
    strategy: TradingStrategy,
    bar: dict,
    open_price: float,
    close: float,
    date: str,
    risk_per_trade: float,
) -> None:
    """Generate and handle strategy signals for the current bar."""
    signal = strategy.on_bar(bar, state.position.to_dict())

    if (
        signal.direction == "exit"
        and signal.action in ("buy", "sell")
        and state.position.size != 0
    ):
        state.pending_exit = PendingExit(
            direction=state.position.direction,
            confidence=signal.confidence,
        )
        logger.info(
            "[EXIT-SIGNAL] %s | %s | bar_close=%.2f | queued for next open",
            date,
            state.position.direction.upper(),
            close,
        )
        return

    if (
        state.position.size == 0
        and signal.action in ("buy", "sell")
        and signal.direction in ("long", "short")
    ):
        portfolio_val = PositionExecutor.portfolio_value(state, open_price)
        requested_size = signal.position_size if signal.position_size > 0 else 0
        logger.info(
            "[SIGNAL] %s | %s | bar_close=%.2f bar_open=%.2f | "
            "port_val=%.2f | requested_size=%d | stop=%.2f target=%.2f",
            date,
            signal.direction.upper(),
            close,
            open_price,
            portfolio_val,
            requested_size,
            signal.stop_price,
            signal.target_price,
        )
        state.pending_entry = PendingEntry(
            direction=signal.direction,
            stop_price=signal.stop_price,
            target_price=signal.target_price,
            position_size=requested_size,
            explicit_size=signal.position_size > 0,
            risk_per_trade=risk_per_trade,
            signal_close=close,
        )


def _track_equity(
    state: BacktestLoopState,
    close: float,
    date: str,
    executor: PositionExecutor,
) -> None:
    """Record portfolio value and drawdown for the equity curve."""
    portfolio_value = PositionExecutor.portfolio_value(state, close)
    if portfolio_value > state.peak_value:
        state.peak_value = portfolio_value
    drawdown = (
        (state.peak_value - portfolio_value) / state.peak_value
        if state.peak_value > 0
        else 0
    )
    state.equity_curve.append(
        {
            "date": date,
            "close": close,
            "value": portfolio_value,
            "drawdown": drawdown,
            "position": state.position.size,
        }
    )


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------


def _precompute_dates(index) -> list[str]:
    """Build the per-bar ISO date strings for an index in one pass.

    Replaces per-bar _bar_date(row) which allocated a Series via df.iloc[i]
    and read row.name. DatetimeIndex values are formatted with a time
    component only when they actually carry one; non-datetime index values
    fall back to their string form.
    """
    values = list(index) if hasattr(index, "__iter__") else [index]
    out: list[str] = []
    for ts in values:
        if ts is None:
            out.append("")
            continue
        if hasattr(ts, "hour") and hasattr(ts, "strftime"):
            if ts.hour or ts.minute or ts.second or ts.microsecond:
                out.append(str(ts.strftime("%Y-%m-%dT%H:%M:%S")))
            else:
                out.append(str(ts.strftime("%Y-%m-%d")))
        else:
            out.append(str(ts))
    return out


def _log_run_summary(state: BacktestLoopState) -> None:
    """Log a summary of the completed backtest run."""
    total_trades = len(state.trades)
    if total_trades == 0:
        logger.info("[SUMMARY] No trades executed. Final cash=%.2f", state.cash)
        return
    winning = sum(1 for t in state.trades if t["pnl"] > 0)
    losing = sum(1 for t in state.trades if t["pnl"] <= 0)
    gross_profit = sum(t["pnl"] for t in state.trades if t["pnl"] > 0)
    gross_loss = sum(t["pnl"] for t in state.trades if t["pnl"] <= 0)
    total_pnl = gross_profit + gross_loss
    logger.info(
        "[SUMMARY] Trades=%d (W=%d L=%d) | WinRate=%.1f%% | "
        "GrossProfit=%.2f GrossLoss=%.2f NetPnL=%.2f | "
        "FinalCash=%.2f PeakValue=%.2f",
        total_trades,
        winning,
        losing,
        (winning / total_trades * 100) if total_trades > 0 else 0,
        gross_profit,
        gross_loss,
        total_pnl,
        state.cash,
        state.peak_value,
    )


def _error_result(message: str) -> dict:
    """Build an error result dict."""
    return {"strategy_name": "", "error": message}
