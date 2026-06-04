"""BacktestRunner — bar-by-bar backtest engine implementing BacktestEngine(ABC).

Template Method pattern: the engine defines a fixed skeleton
(init → loop bars → call strategy → execute signals → compute metrics).
The strategy varies via the Strategy pattern.

BacktestResultDTO by the use case.
"""

from __future__ import annotations

import logging

import pandas as pd

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

logger = logging.getLogger(__name__)


class BacktestRunner(BacktestEngine):
    """Bar-by-bar backtest runner for any bar interval.

    Supports long and short positions, conservative entry (next-bar open),
    stop-loss and take-profit execution, and full equity curve tracking.
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
            **params: Strategy parameters forwarded via __init__ if needed.

        Returns:
            Dict with backtest results (strategy_name, symbol, total_return,
            sharpe_ratio, trades, equity_curve, ...).
        """
        if df.empty:
            return _error_result("No bars provided")

        # Reset strategy state
        strategy.on_reset()

        result = _run_loop(df, strategy, initial_cash)
        return _build_result_dict(strategy, result, initial_cash)


# ---------------------------------------------------------------------------
# Internal state for the bar loop
# ---------------------------------------------------------------------------


class _Position:
    """Tracks an open position during the bar loop."""

    __slots__ = (
        "size",
        "direction",
        "entry_price",
        "entry_date",
        "stop_price",
        "target_price",
        "bars_held",
    )

    def __init__(self):
        self.size: int = 0
        self.direction: str = ""
        self.entry_price: float = 0.0
        self.entry_date: str = ""
        self.stop_price: float = 0.0
        self.target_price: float = 0.0
        self.bars_held: int = 0

    def to_dict(self) -> dict:
        return {
            "size": self.size,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "entry_date": self.entry_date,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "bars_held": self.bars_held,
        }

    def reset(self):
        self.size = 0
        self.direction = ""
        self.entry_price = 0.0
        self.entry_date = ""
        self.stop_price = 0.0
        self.target_price = 0.0
        self.bars_held = 0


class _LoopState:
    """Mutable state carried through the bar loop."""

    __slots__ = (
        "cash",
        "position",
        "trades",
        "equity_curve",
        "pending_signal",
        "peak_value",
    )

    def __init__(self, initial_cash: float):
        self.cash = initial_cash
        self.position = _Position()
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.pending_signal: dict | None = None
        self.peak_value = initial_cash


# ---------------------------------------------------------------------------
# Bar loop
# ---------------------------------------------------------------------------


def _run_loop(
    df: pd.DataFrame,
    strategy: TradingStrategy,
    initial_cash: float,
) -> _LoopState:
    """Iterate bars, call strategy, execute signals, track positions."""
    state = _LoopState(initial_cash)

    for i in range(len(df)):
        row = df.iloc[i]
        bar_dict = _row_to_bar(row)
        bar_date = _bar_date(row)
        close = float(row["close"])
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])

        # --- Execute pending entry (conservative mode: next-bar open) ---
        if state.pending_signal is not None and state.position.size == 0:
            sig = state.pending_signal
            state.pending_signal = None
            _enter_position(state, sig, open_price, bar_date)

        # --- Check stop/target for existing position ---
        if state.position.size != 0:
            _check_exit_conditions(state, close, high, low, bar_date)

        # --- Generate signal from strategy ---
        signal = strategy.on_bar(bar_dict, state.position.to_dict())

        # --- Handle signal exit ---
        if (
            signal.action == "sell"
            and signal.direction == "exit"
            and state.position.size != 0
        ):
            _exit_position(state, close, bar_date)

        # --- Handle entry signals ---
        elif (
            state.position.size == 0
            and signal.action in ("buy", "sell")
            and signal.direction in ("long", "short")
        ):
            # Conservative mode: defer entry to next bar
            state.pending_signal = {
                "direction": signal.direction,
                "stop_price": signal.stop_price,
                "target_price": signal.target_price,
                "position_size": 100,
            }

        # --- Track equity ---
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
                "date": bar_date,
                "value": portfolio_value,
                "drawdown": drawdown,
                "position": state.position.size,
            }
        )

    return state


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


def _enter_position(state: _LoopState, sig: dict, price: float, date: str):
    """Enter a new position from a pending signal."""
    size = sig["position_size"] or 100
    if sig["direction"] == "long":
        state.cash -= size * price
        state.position = _Position()
        state.position.size = size
        state.position.direction = "long"
    elif sig["direction"] == "short":
        state.cash += size * price
        state.position = _Position()
        state.position.size = -size
        state.position.direction = "short"
    state.position.entry_price = price
    state.position.entry_date = date
    state.position.stop_price = sig["stop_price"]
    state.position.target_price = sig["target_price"]


def _exit_position(state: _LoopState, exit_price: float, bar_date: str):
    """Close the current position and record the trade."""
    abs_size = abs(state.position.size)
    if state.position.size > 0:
        pnl = (exit_price - state.position.entry_price) * abs_size
        state.cash += abs_size * exit_price
    else:
        pnl = (state.position.entry_price - exit_price) * abs_size
        state.cash -= abs_size * exit_price

    pnl_pct = (
        pnl / (state.position.entry_price * abs_size)
        if state.position.entry_price > 0 and abs_size > 0
        else 0.0
    )
    state.trades.append(
        {
            "entry_date": state.position.entry_date,
            "exit_date": bar_date,
            "entry_price": state.position.entry_price,
            "exit_price": exit_price,
            "size": abs_size,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "duration_bars": state.position.bars_held,
            "metadata": {"direction": state.position.direction},
        }
    )
    state.position.reset()


def _check_exit_conditions(
    state: _LoopState,
    close: float,
    high: float,
    low: float,
    bar_date: str,
):
    """Check stop-loss and take-profit for the open position."""
    state.position.bars_held += 1
    exit_price: float | None = None

    if state.position.size > 0:  # Long
        if state.position.stop_price > 0 and low <= state.position.stop_price:
            exit_price = state.position.stop_price
        elif state.position.target_price > 0 and high >= state.position.target_price:
            exit_price = state.position.target_price
    elif state.position.size < 0:  # Short
        if state.position.stop_price > 0 and high >= state.position.stop_price:
            exit_price = state.position.stop_price
        elif state.position.target_price > 0 and low <= state.position.target_price:
            exit_price = state.position.target_price

    if exit_price is not None:
        _exit_position(state, exit_price, bar_date)


def _portfolio_value(state: _LoopState, close: float) -> float:
    """Calculate current portfolio value."""
    if state.position.size > 0:
        return state.cash + state.position.size * close
    elif state.position.size < 0:
        return state.cash - abs(state.position.size) * close
    return state.cash


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------


def _row_to_bar(row: pd.Series) -> dict:
    """Convert a DataFrame row to a plain dict for strategy.on_bar()."""
    bar = row.to_dict()
    # Ensure OHLCV fields are plain floats (not numpy)
    for key in ("open", "high", "low", "close", "volume"):
        val = bar.get(key)
        if val is not None and hasattr(val, "item"):
            bar[key] = val.item()
    return bar


def _bar_date(row: pd.Series) -> str:
    """Extract ISO date string from a DataFrame row's index."""
    ts = row.name if row.name is not None else row.get("timestamp")
    if ts is None:
        return ""
    if hasattr(ts, "strftime"):
        return str(ts.strftime("%Y-%m-%d"))
    return str(ts)[:10]


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


def _build_result_dict(
    strategy: TradingStrategy,
    state: _LoopState,
    initial_cash: float,
) -> dict:
    """Compute metrics and build the result dict from loop state."""
    equity_values = [e["value"] for e in state.equity_curve]
    final_value = equity_values[-1] if equity_values else initial_cash

    daily_returns = (
        calculate_daily_returns(equity_values) if len(equity_values) > 1 else []
    )
    total_return = calculate_total_return(initial_cash, final_value)
    max_dd = calculate_max_drawdown(equity_values) if equity_values else 0.0
    sharpe = calculate_sharpe(daily_returns) if daily_returns else 0.0
    sortino = calculate_sortino(daily_returns) if daily_returns else 0.0

    gross_profit = sum(t["pnl"] for t in state.trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in state.trades if t["pnl"] <= 0))
    profit_factor = calculate_profit_factor(gross_profit, gross_loss)

    trading_days = len(state.equity_curve)
    annualised_return = calculate_annualised_return(total_return, trading_days)
    calmar = calculate_calmar_ratio(annualised_return, max_dd)

    winning = sum(1 for t in state.trades if t["pnl"] > 0)
    losing = sum(1 for t in state.trades if t["pnl"] <= 0)
    total_trades = len(state.trades)
    win_rate = winning / total_trades if total_trades > 0 else 0.0

    meta = strategy.meta()

    # Determine date range from equity curve
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
        "trades": state.trades,
        "equity_curve": state.equity_curve,
    }


def _error_result(message: str) -> dict:
    """Build an error result dict."""
    return {"strategy_name": "", "error": message}
