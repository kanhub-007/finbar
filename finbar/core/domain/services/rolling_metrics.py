"""Rolling metrics calculator — pure functions for bar-level analytics.

No dependencies on pandas, numpy, or infrastructure. Takes plain lists
and returns plain dicts. Used by BacktestResultBuilder.
"""

from collections.abc import Sequence
from typing import Any


def calculate_rolling_sharpe(
    equity_values: Sequence[float],
    window: int = 60,
    periods_per_year: float = 252.0,
) -> list[float | None]:
    """Compute rolling Sharpe ratio over a sliding window.

    Returns a list the same length as equity_values. Values before the
    window has enough data are None.

    Args:
        equity_values: Portfolio value at each bar.
        window: Rolling window size in bars.
        periods_per_year: Annualization factor.

    Returns:
        List of annualized rolling Sharpe values, or None for bars < window.
    """
    if len(equity_values) < 2:
        return [None] * len(equity_values)

    result: list[float | None] = [None] * len(equity_values)
    returns = _daily_returns(equity_values)

    for i in range(window - 1, len(returns)):
        window_returns = returns[i - window + 1 : i + 1]
        if len(window_returns) < 2:
            continue
        mean_ret = sum(window_returns) / len(window_returns)
        n_ret = len(window_returns)
        var = sum((r - mean_ret) ** 2 for r in window_returns) / (n_ret - 1)
        if var <= 0:
            result[i + 1] = 0.0
            continue
        std = var**0.5
        result[i + 1] = round(mean_ret / std * (periods_per_year**0.5), 4)

    return result


def calculate_rolling_win_rate(
    trades: Sequence[dict[str, Any]],
    equity_curve: Sequence[dict[str, Any]],
    window: int = 60,
) -> list[float | None]:
    """Compute rolling win rate over a sliding window of bars.

    For each bar, looks back `window` bars and counts trades closed
    in that period, computing the fraction that were profitable.

    Returns a list the same length as equity_curve.
    """
    n = len(equity_curve)
    result: list[float | None] = [None] * n

    if not trades or n < 2:
        return result

    bar_dates = [e.get("date", "") for e in equity_curve]
    trade_exit_indices: list[int] = []
    trade_wins: list[bool] = []

    for t in trades:
        exit_date = str(t.get("exit_date", ""))
        try:
            idx = bar_dates.index(exit_date)
            trade_exit_indices.append(idx)
            trade_wins.append(float(t.get("pnl", 0)) > 0)
        except ValueError:
            pass

    if not trade_exit_indices:
        return result

    for i in range(window, n):
        window_end = i
        window_start = max(0, i - window + 1)
        wins_in_window = 0
        total_in_window = 0
        for exit_idx, is_win in zip(trade_exit_indices, trade_wins):
            if window_start <= exit_idx <= window_end:
                total_in_window += 1
                if is_win:
                    wins_in_window += 1
        if total_in_window > 0:
            result[i] = round(wins_in_window / total_in_window, 4)

    return result


def calculate_rolling_drawdown(
    equity_values: Sequence[float],
) -> list[float]:
    """Compute drawdown at each bar (negative values = underwater).

    Returns a list the same length as equity_values.
    """
    if not equity_values:
        return []

    result: list[float] = []
    peak = equity_values[0]
    for val in equity_values:
        peak = max(peak, val)
        dd = (val - peak) / peak if peak > 0 else 0.0
        result.append(round(dd, 4))

    return result


def calculate_rolling_pnl(
    equity_values: Sequence[float],
    window: int = 60,
) -> list[float | None]:
    """Compute bar-by-bar rolling PnL changes.

    Returns per-bar returns multiplied by portfolio value at start of
    each bar.
    """
    n = len(equity_values)
    result: list[float | None] = [None] * n
    if n < 2:
        return result

    for i in range(1, n):
        if equity_values[i - 1] == 0:
            result[i] = 0.0
            continue
        bar_return = (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
        result[i] = round(bar_return * equity_values[i - 1], 2)

    return result


def calculate_monthly_returns(
    equity_curve: Sequence[dict[str, Any]],
) -> dict[str, float]:
    """Compute calendar-month returns from the equity curve.

    Returns dict mapping "YYYY-MM" to total return for that month.
    """
    if not equity_curve:
        return {}

    months: dict[str, list[float]] = {}
    for e in equity_curve:
        date_str = str(e.get("date", ""))
        if len(date_str) >= 7:
            month_key = date_str[:7]
            if month_key not in months:
                months[month_key] = []
            months[month_key].append(e.get("value", 0.0))

    result: dict[str, float] = {}
    for month_key in sorted(months):
        values = months[month_key]
        if not values:
            continue
        month_start = values[0]
        month_end = values[-1]
        if month_start > 0:
            result[month_key] = round((month_end - month_start) / month_start, 4)

    return result


def calculate_yearly_returns(
    equity_curve: Sequence[dict[str, Any]],
) -> dict[str, float]:
    """Compute calendar-year returns from the equity curve.

    Returns dict mapping "YYYY" to total return for that year.
    """
    monthly = calculate_monthly_returns(equity_curve)
    years: dict[str, list[float]] = {}
    for month_key, ret in monthly.items():
        year = month_key[:4]
        if year not in years:
            years[year] = []
        years[year].append(ret)

    result: dict[str, float] = {}
    for year in sorted(years):
        rets = years[year]
        compound = 1.0
        for r in rets:
            compound *= 1.0 + r
        result[year] = round(compound - 1.0, 4)

    return result


def calculate_exposure(
    equity_curve: Sequence[dict[str, Any]],
) -> list[float]:
    """Compute position exposure fraction at each bar.

    Returns fraction of equity deployed (0.0 = all cash, 1.0 = fully invested).
    """
    if not equity_curve:
        return []

    result: list[float] = []
    for e in equity_curve:
        position_size = abs(float(e.get("position", 0) or 0))
        value = float(e.get("value", 0) or 1)
        if value > 0:
            close_price = float(e.get("close", 0) or 0)
            deployed = position_size * close_price if close_price else 0
            result.append(round(min(deployed / value, 1.0), 4))
        else:
            result.append(0.0)

    return result


def calculate_trade_distribution(
    trades: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Compute trade PnL and duration distribution statistics.

    Returns dict with bin edges, counts, and summary percentiles.
    """
    if not trades:
        return {
            "pnl_bins": [],
            "pnl_counts": [],
            "pnl_percentiles": {},
            "duration_bins": [],
            "duration_counts": [],
            "duration_percentiles": {},
            "avg_pnl": 0.0,
            "avg_duration": 0.0,
        }

    pnls = [float(t.get("pnl", 0) or 0) for t in trades]
    durations = [float(t.get("duration_bars", 0) or 0) for t in trades]

    pnl_hist = _histogram(pnls, bins=10)
    dur_hist = _histogram(durations, bins=8)

    sorted_pnls = sorted(pnls)
    sorted_durs = sorted(durations)

    return {
        "pnl_bins": pnl_hist["bin_edges"],
        "pnl_counts": pnl_hist["counts"],
        "pnl_percentiles": _percentiles(sorted_pnls),
        "duration_bins": dur_hist["bin_edges"],
        "duration_counts": dur_hist["counts"],
        "duration_percentiles": _percentiles(sorted_durs),
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
        "avg_duration": round(sum(durations) / len(durations), 1),
    }


def _daily_returns(equity_values: Sequence[float]) -> list[float]:
    """Compute bar-to-bar returns."""
    if len(equity_values) < 2:
        return []
    result: list[float] = []
    for i in range(1, len(equity_values)):
        if equity_values[i - 1] == 0:
            result.append(0.0)
        else:
            prev = equity_values[i - 1]
            curr = equity_values[i]
            ret = (curr - prev) / prev
            result.append(ret)
    return result


def _histogram(values: list[float], bins: int = 10) -> dict:
    """Compute histogram bins and counts from a list of floats."""
    if not values:
        return {"bin_edges": [], "counts": []}

    min_val = min(values)
    max_val = max(values)
    if min_val == max_val:
        bin_edges = [min_val, max_val + 1]
        counts = [len(values)]
        return {"bin_edges": [round(e, 2) for e in bin_edges], "counts": counts}

    range_val = max_val - min_val
    bin_width = range_val / bins
    bin_edges = [min_val + i * bin_width for i in range(bins + 1)]
    bin_edges = [round(e, 2) for e in bin_edges]

    counts = [0] * bins
    for v in values:
        if v == max_val:
            counts[-1] += 1
        else:
            idx = int((v - min_val) / bin_width)
            idx = min(idx, bins - 1)
            counts[idx] += 1

    return {"bin_edges": bin_edges, "counts": counts}


def _percentiles(sorted_values: list[float]) -> dict[str, float]:
    """Compute p25, p50, p75, p90, p95, p99 from sorted values."""
    if not sorted_values:
        return {}
    n = len(sorted_values)

    def _p(pct: float) -> float:
        idx = int(n * pct / 100)
        idx = min(idx, n - 1)
        return round(sorted_values[idx], 2)

    return {
        "p25": _p(25),
        "p50": _p(50),
        "p75": _p(75),
        "p90": _p(90),
        "p95": _p(95),
        "p99": _p(99),
    }
