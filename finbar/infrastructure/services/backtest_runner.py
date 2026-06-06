"""BacktestRunner — bar-by-bar backtest engine implementing BacktestEngine(ABC).

Template Method pattern: the engine defines a fixed skeleton
(init → loop bars → call strategy → execute signals → compute metrics).
The strategy varies via the Strategy pattern.

BacktestResultDTO by the use case.
"""

from __future__ import annotations

import logging

import pandas as pd

from finbar.core.domain.entities.pending_entry import PendingEntry
from finbar.core.domain.entities.pending_exit import PendingExit
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
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
from finbar.infrastructure.services.backtest_data_validator import (
    validate_backtest_frame,
)
from finbar.infrastructure.services.backtest_loop_state import BacktestLoopState
from finbar.infrastructure.services.backtest_position import BacktestPosition

logger = logging.getLogger(__name__)


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

        Args:
            df: DataFrame with OHLCV + indicator columns, datetime index.
            strategy: TradingStrategy instance.
            initial_cash: Starting capital.
            **params: Engine/strategy parameters such as interval and risk.

        Returns:
            Dict with backtest results (strategy_name, symbol, total_return,
            sharpe_ratio, trades, equity_curve, ...).
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
        result = _run_loop(
            df,
            strategy,
            initial_cash,
            risk_per_trade,
            commission_pct,
            slippage_pct,
        )
        return _build_result_dict(
            strategy,
            result,
            initial_cash,
            interval,
            warmup_bars,
            first_tradable,
            commission_pct,
            slippage_pct,
        )


# ---------------------------------------------------------------------------
# Bar loop
# ---------------------------------------------------------------------------


def _run_loop(
    df: pd.DataFrame,
    strategy: TradingStrategy,
    initial_cash: float,
    risk_per_trade: float = 0.02,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> BacktestLoopState:
    """Iterate bars, call strategy, execute signals, track positions."""
    state = BacktestLoopState(initial_cash)
    final_close = 0.0
    final_date = ""

    for i in range(len(df)):
        row = df.iloc[i]
        bar_date = _bar_date(row)
        close = float(row["close"])
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        final_close = close
        final_date = bar_date

        bar_dict = _row_to_bar(row)
        _execute_pending(state, open_price, bar_date, commission_pct, slippage_pct)
        _check_exit_conditions(
            state, open_price, close, high, low, bar_date, commission_pct, slippage_pct
        )
        _process_signal(
            state,
            strategy,
            bar_dict,
            open_price,
            close,
            bar_date,
            risk_per_trade,
            commission_pct,
            slippage_pct,
        )
        _track_equity(state, close, bar_date)

    _liquidate_open_position(
        state, final_close, final_date, commission_pct, slippage_pct
    )
    _log_run_summary(state)
    return state


def _execute_pending(
    state: BacktestLoopState,
    price: float,
    date: str,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> None:
    """Execute pending exit/entry signals at next bar's open."""
    if state.pending_exit is not None and state.position.size != 0:
        _exit_position(
            state,
            price,
            date,
            exit_reason="signal_exit_next_open",
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        state.pending_exit = None

    if state.pending_entry is None or state.position.size != 0:
        return
    entry = state.pending_entry
    state.pending_entry = None
    _enter_position(state, entry, price, date, commission_pct, slippage_pct)


def _process_signal(
    state: BacktestLoopState,
    strategy: TradingStrategy,
    bar: dict,
    open_price: float,
    close: float,
    date: str,
    risk_per_trade: float,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
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
        portfolio_val = _portfolio_value(state, open_price)
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
        )


def _track_equity(state: BacktestLoopState, close: float, date: str) -> None:
    """Record portfolio value and drawdown for the equity curve."""
    portfolio_value = _portfolio_value(state, close)
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
# Execution helpers
# ---------------------------------------------------------------------------


def _enter_position(
    state: BacktestLoopState,
    entry: PendingEntry,
    price: float,
    date: str,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> None:
    """Enter a new position from a pending entry signal."""
    if not _protective_stop_valid(entry, price):
        logger.info(
            "[ENTRY-SKIP] %s | %s | price=%.2f invalid stop=%.2f",
            date,
            entry.direction.upper(),
            price,
            entry.stop_price,
        )
        return

    size = _resolve_entry_size(entry, price, _portfolio_value(state, price))
    if size <= 0:
        return

    cash_before = state.cash
    if not entry.explicit_size and entry.direction == "long" and price > 0:
        max_affordable = int(state.cash / price) if state.cash > 0 else 0
        if max_affordable <= 0:
            return
        size = min(size, max_affordable)

    fill_price = _apply_slippage(price, slippage_pct, entry.direction, "entry")
    cost = size * fill_price
    commission = _commission_cost(cost, commission_pct)
    state.total_commission += commission
    state.total_slippage += abs(fill_price - price) * size

    if entry.direction == "long":
        state.cash -= cost + commission
        state.position = BacktestPosition()
        state.position.size = size
        state.position.direction = "long"
    elif entry.direction == "short":
        state.cash += cost - commission
        state.position = BacktestPosition()
        state.position.size = -size
        state.position.direction = "short"
    else:
        return

    state.position.entry_price = fill_price
    state.position.entry_date = date
    state.position.stop_price = entry.stop_price
    state.position.target_price = entry.target_price
    logger.info(
        "[ENTRY] %s | %s | price=%.2f size=%s cost=%.2f | "
        "cash: %.2f->%.2f (d=%.2f) | stop=%.2f target=%.2f",
        date,
        entry.direction.upper(),
        fill_price,
        size,
        cost,
        cash_before,
        state.cash,
        state.cash - cash_before,
        entry.stop_price,
        entry.target_price,
    )


def _exit_position(
    state: BacktestLoopState,
    exit_price: float,
    bar_date: str,
    exit_reason: str = "signal",
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> None:
    """Close the current position and record the trade."""
    abs_size = abs(state.position.size)
    cash_before = state.cash
    entry_price = state.position.entry_price
    entry_date = state.position.entry_date
    direction = state.position.direction

    fill_price = _apply_slippage(exit_price, slippage_pct, direction, "exit")
    fill_cost = abs_size * fill_price
    commission = _commission_cost(fill_cost, commission_pct)
    state.total_commission += commission
    state.total_slippage += abs(fill_price - exit_price) * abs_size

    if state.position.size > 0:
        pnl = (fill_price - entry_price) * abs_size
        state.cash += fill_cost - commission
    else:
        pnl = (entry_price - fill_price) * abs_size
        state.cash -= fill_cost + commission

    pnl_pct = (
        pnl / (entry_price * abs_size) if entry_price > 0 and abs_size > 0 else 0.0
    )
    state.trades.append(
        {
            "entry_date": entry_date,
            "exit_date": bar_date,
            "entry_price": entry_price,
            "exit_price": fill_price,
            "size": abs_size,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "duration_bars": state.position.bars_held,
            "metadata": {"direction": direction, "exit_reason": exit_reason},
        }
    )
    logger.info(
        "[EXIT]  %s | %s | exit=%.2f entry=%.2f size=%s | "
        "PnL=%.2f (%.2f%%) | cash: %.2f->%.2f (d=%.2f) | "
        "bars=%d reason=%s",
        bar_date,
        direction.upper(),
        exit_price,
        entry_price,
        abs_size,
        pnl,
        pnl_pct * 100,
        cash_before,
        state.cash,
        state.cash - cash_before,
        state.position.bars_held,
        exit_reason,
    )
    state.position.reset()


def _check_exit_conditions(
    state: BacktestLoopState,
    open_price: float,
    close: float,
    high: float,
    low: float,
    bar_date: str,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> None:
    """Check gap-aware stop-loss and take-profit for the open position."""
    state.position.bars_held += 1
    fill = _resolve_intrabar_exit(state.position, open_price, high, low)
    if fill is not None:
        exit_price, reason = fill
        _exit_position(
            state,
            exit_price,
            bar_date,
            exit_reason=reason,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )


def _resolve_intrabar_exit(
    position: BacktestPosition,
    open_price: float,
    high: float,
    low: float,
) -> tuple[float, str] | None:
    """Return gap-aware exit fill for stop/target orders, if touched."""
    stop = position.stop_price
    target = position.target_price
    if position.size > 0:
        return _resolve_long_exit(open_price, high, low, stop, target)
    if position.size < 0:
        return _resolve_short_exit(open_price, high, low, stop, target)
    return None


def _resolve_long_exit(
    open_price: float,
    high: float,
    low: float,
    stop: float,
    target: float,
) -> tuple[float, str] | None:
    """Return conservative long stop/target fill for one bar."""
    if stop > 0 and open_price <= stop:
        return open_price, "stop_loss_gap"
    if target > 0 and open_price >= target:
        return open_price, "take_profit_gap"
    stop_hit = stop > 0 and low <= stop
    target_hit = target > 0 and high >= target
    if stop_hit:
        return stop, "stop_loss"
    if target_hit:
        return target, "take_profit"
    return None


def _resolve_short_exit(
    open_price: float,
    high: float,
    low: float,
    stop: float,
    target: float,
) -> tuple[float, str] | None:
    """Return conservative short stop/target fill for one bar."""
    if stop > 0 and open_price >= stop:
        return open_price, "stop_loss_gap"
    if target > 0 and open_price <= target:
        return open_price, "take_profit_gap"
    stop_hit = stop > 0 and high >= stop
    target_hit = target > 0 and low <= target
    if stop_hit:
        return stop, "stop_loss"
    if target_hit:
        return target, "take_profit"
    return None


def _liquidate_open_position(
    state: BacktestLoopState,
    final_close: float,
    final_date: str,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> None:
    """Close any open position at the final bar close for metric consistency."""
    if state.position.size == 0 or not final_date:
        return
    _exit_position(
        state,
        final_close,
        final_date,
        exit_reason="end_of_backtest",
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )
    if state.equity_curve:
        last = state.equity_curve[-1]
        last["value"] = _portfolio_value(state, final_close)
        last["position"] = 0
        if last["value"] > state.peak_value:
            state.peak_value = last["value"]
        last["drawdown"] = (
            (state.peak_value - last["value"]) / state.peak_value
            if state.peak_value > 0
            else 0.0
        )


def _portfolio_value(state: BacktestLoopState, close: float) -> float:
    """Calculate current portfolio value."""
    if state.position.size > 0:
        return state.cash + state.position.size * close
    if state.position.size < 0:
        return state.cash - abs(state.position.size) * close
    return state.cash


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------


def _row_to_bar(row: pd.Series) -> dict:
    """Convert a DataFrame row to a plain dict for strategy.on_bar()."""
    bar = row.to_dict()
    for key in ("open", "high", "low", "close", "volume"):
        val = bar.get(key)
        if val is not None and hasattr(val, "item"):
            bar[key] = val.item()
    return bar


def _bar_date(row: pd.Series) -> str:
    """Extract an ISO timestamp from a DataFrame row's index."""
    ts = row.name if row.name is not None else row.get("timestamp")
    if ts is None:
        return ""
    if hasattr(ts, "hour") and hasattr(ts, "strftime"):
        if ts.hour or ts.minute or ts.second or ts.microsecond:
            return str(ts.strftime("%Y-%m-%dT%H:%M:%S"))
        return str(ts.strftime("%Y-%m-%d"))
    return str(ts)


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


def _build_result_dict(
    strategy: TradingStrategy,
    state: BacktestLoopState,
    initial_cash: float,
    interval: str = "",
    warmup_bars: int = 0,
    first_tradable: str = "",
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> dict:
    """Compute metrics and build the result dict from loop state."""
    equity_values = [e["value"] for e in state.equity_curve]
    final_value = equity_values[-1] if equity_values else initial_cash
    annualization_factor = _annualization_factor(interval)

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
        "total_slippage": round(state.total_slippage, 2),
        "commission_pct": round(commission_pct, 6),
        "slippage_pct": round(slippage_pct, 6),
        "trades": state.trades,
        "equity_curve": state.equity_curve,
        "trust_diagnostics": {
            "gap_aware_fills": True,
            "lookahead_safe_mtf": True,
            "liquidated_on_close": True,
            "entry_model": "next_bar_open",
            "exit_model": "next_bar_open",
            "cost_model": (
                "commission_and_slippage"
                if commission_pct > 0 or slippage_pct > 0
                else "zero_cost"
            ),
            "warmup_bars": warmup_bars,
            "first_tradable": first_tradable,
            "commission_pct": round(commission_pct, 6),
            "slippage_pct": round(slippage_pct, 6),
            "annualization_factor": annualization_factor,
        },
    }


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


# ── Position sizing ──────────────────────────────────────────────────────

_DEFAULT_POSITION_SIZE = 100
_DEFAULT_RISK_PER_TRADE = 0.02


def _protective_stop_valid(entry: PendingEntry, entry_price: float) -> bool:
    """Return False when the entry opens beyond the intended protective stop."""
    if entry.stop_price <= 0:
        return True
    if entry.direction == "long":
        return entry.stop_price < entry_price
    if entry.direction == "short":
        return entry.stop_price > entry_price
    return False


def _resolve_entry_size(
    entry: PendingEntry,
    entry_price: float,
    portfolio_value: float,
) -> int:
    """Compute position size from explicit size or actual fill-price risk."""
    if entry.explicit_size and entry.position_size > 0:
        return entry.position_size

    if entry.stop_price > 0:
        risk_amount = portfolio_value * entry.risk_per_trade
        risk_per_share = abs(entry_price - entry.stop_price)
        if risk_per_share > 0.001:
            return max(1, int(risk_amount / risk_per_share))

    return _DEFAULT_POSITION_SIZE


def _apply_slippage(
    price: float,
    slippage_pct: float,
    direction: str,
    side: str,
) -> float:
    """Return fill price adjusted by directional slippage."""
    if slippage_pct <= 0:
        return price
    if direction == "long":
        factor = 1.0 + slippage_pct if side == "entry" else 1.0 - slippage_pct
    elif direction == "short":
        factor = 1.0 - slippage_pct if side == "entry" else 1.0 + slippage_pct
    else:
        return price
    return price * factor


def _commission_cost(gross: float, commission_pct: float) -> float:
    """Return absolute commission cost for a transaction."""
    if commission_pct <= 0:
        return 0.0
    return abs(gross) * commission_pct


def _annualization_factor(interval: str) -> float:
    """Return approximate periods per year for the supplied bar interval."""
    normalized = interval.lower().strip()
    factors = {
        "1d": 252.0,
        "1w": 52.0,
        "1h": 252.0 * 6.5,
        "30min": 252.0 * 13.0,
        "5min": 252.0 * 78.0,
    }
    return factors.get(normalized, 252.0)
