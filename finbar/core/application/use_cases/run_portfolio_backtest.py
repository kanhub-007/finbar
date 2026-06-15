"""RunPortfolioBacktestUseCase — execute a multi-asset portfolio backtest."""

from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import (
    BarFrameConverter,
)

from finbar.core.application.dto.portfolio_backtest_request import (
    PortfolioBacktestRequest,
)
from finbar.core.domain.entities.portfolio_result import PortfolioResult
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.services.annualization import (
    annualization_factor as _annualization_factor,
)
from finbar.core.domain.services.correlation import pearson as _pearson


class RunPortfolioBacktestUseCase:
    """Run independent backtests per asset and aggregate into portfolio result.

    Each asset receives capital proportional to its weight, runs its
    assigned strategy, and produces an equity curve. The portfolio curve
    is the sum of all individual curves.
    """

    def __init__(
        self,
        strategy_provider: StrategyProvider,
        engine: BacktestEngine,
        converter: BarFrameConverter,
    ):
        """Create the use case."""
        self._strategy_provider = strategy_provider
        self._engine = engine
        self._converter = converter

    def execute(self, request: PortfolioBacktestRequest) -> PortfolioResult:
        """Run all asset backtests and aggregate into portfolio results."""
        if not request.assets:
            return PortfolioResult(error="No assets in portfolio")

        total_weight = sum(a.weight for a in request.assets)
        if total_weight <= 0:
            return PortfolioResult(error="Total portfolio weight must be positive")

        per_asset: dict = {}
        equity_curves: dict[str, list[dict]] = {}
        all_returns: dict[str, dict[str, float]] = {}
        errors: list[str] = []

        for asset in request.assets:
            strategy = self._strategy_provider.create(asset.strategy_name)
            if strategy is None:
                errors.append(f"Strategy not found: {asset.strategy_name}")
                continue

            if not asset.bars:
                errors.append(f"No bars for: {asset.symbol}")
                continue

            frame = self._converter.bars_to_frame(asset.bars)
            if frame is None or len(frame) == 0:
                errors.append(f"Empty frame for: {asset.symbol}")
                continue

            allocated_cash = request.initial_cash * (asset.weight / total_weight)

            try:
                raw = self._engine.run(
                    df=frame,
                    strategy=strategy,
                    initial_cash=allocated_cash,
                    interval=request.interval,
                    risk_per_trade=request.risk_per_trade,
                    leverage=request.execution.leverage_multiplier,
                    risk_mode=request.execution.risk_mode,
                    commission_pct=request.execution.commission_pct,
                    slippage_pct=request.execution.slippage_pct,
                    cap_explicit_size=request.execution.cap_explicit_size,
                    reject_oversized_explicit_orders=(
                        request.execution.reject_oversized_explicit_orders
                    ),
                    allow_negative_cash=request.execution.allow_negative_cash,
                    market_calendar=request.execution.market_calendar,
                    borrow_fee_annual_pct=(request.execution.borrow_fee_annual_pct),
                    margin_mode=request.execution.margin_mode,
                )
                per_asset[asset.symbol] = raw
                eq = raw.get("equity_curve", [])
                if eq:
                    equity_curves[asset.symbol] = eq
                    returns = _compute_returns(eq)
                    if returns:
                        all_returns[asset.symbol] = returns
            except Exception as exc:
                errors.append(f"{asset.symbol}: {exc}")

        if not equity_curves:
            return PortfolioResult(
                error="; ".join(errors) if errors else "All assets failed"
            )

        portfolio_eq, portfolio_metrics = _aggregate_equity(
            equity_curves,
            request.initial_cash,
            request.interval or "1d",
            request.execution.market_calendar,
        )
        corr = _correlation_matrix(list(all_returns.values()))

        return PortfolioResult(
            total_return=portfolio_metrics.get("total_return", 0.0),
            sharpe_ratio=portfolio_metrics.get("sharpe_ratio", 0.0),
            max_drawdown=portfolio_metrics.get("max_drawdown", 0.0),
            equity_curve=portfolio_eq,
            per_asset_results=per_asset,
            correlation_matrix=corr,
        )


def _compute_returns(eq: list[dict]) -> dict[str, float]:
    """Compute bar-to-bar returns from an equity curve, keyed by date.

    Date keys enable correct per-date alignment across assets with
    different bar calendars — avoids correlating the wrong bars together.
    """
    returns: dict[str, float] = {}
    for i in range(1, len(eq)):
        prev = eq[i - 1].get("value", 0)
        curr = eq[i].get("value", 0)
        d = str(eq[i].get("date", ""))
        if prev > 0 and d:
            returns[d] = (curr - prev) / prev
    return returns


def _aggregate_equity(
    curves: dict[str, list[dict]],
    initial_cash: float,
    interval: str,
    market_calendar: str,
) -> tuple[list[dict], dict]:
    """Sum individual equity curves into a portfolio curve."""
    dates = _all_dates(curves)
    if not dates:
        return [], {}

    # Pre-index each asset's curve by date ONCE (O(A*B)) so per-date lookup
    # is O(1) instead of a linear scan of the whole curve per date. The
    # previous implementation was O(A * B^2) because _value_at did two full
    # scans of every asset's curve for every date in the union.
    indexed: dict[str, dict[str, float]] = {}
    first_value: dict[str, float] = {}
    for sym, eq in curves.items():
        first_value[sym] = float(eq[0].get("value", 0) or 0) if eq else 0.0
        indexed[sym] = {
            str(e.get("date", "")): float(e.get("value", 0) or 0) for e in eq
        }

    ordered_dates = sorted(dates)
    # Carry-forward state per asset: last seen value on/before current date.
    carried = dict(first_value)

    portfolio_eq = []
    peak = initial_cash
    for date in ordered_dates:
        total_value = 0.0
        for sym in curves:
            v = indexed[sym].get(date)
            if v is not None:
                carried[sym] = v
            # For dates before the asset's first bar, carry its allocated
            # capital (first value) rather than 0.0.
            total_value += carried.get(sym, first_value[sym])
        if total_value == 0:
            total_value = initial_cash
        drawdown = (peak - total_value) / peak if peak > 0 else 0.0
        peak = max(peak, total_value)
        portfolio_eq.append(
            {
                "date": date,
                "value": round(total_value, 2),
                "drawdown": round(drawdown, 4),
            }
        )

    values = [e["value"] for e in portfolio_eq]
    final_value = values[-1] if values else initial_cash
    total_return = (
        (final_value - initial_cash) / initial_cash if initial_cash > 0 else 0.0
    )

    from finbar.core.domain.services.backtest_metrics import (
        calculate_daily_returns,
        calculate_max_drawdown,
        calculate_sharpe,
    )

    dr = calculate_daily_returns(values) if len(values) > 1 else []
    max_dd = calculate_max_drawdown(values) if values else 0.0

    ann_factor, _ = _annualization_factor(interval, market_calendar)
    sharpe = calculate_sharpe(dr, annualization_factor=ann_factor) if dr else 0.0

    return portfolio_eq, {
        "total_return": round(total_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
    }


def _all_dates(curves: dict[str, list[dict]]) -> set[str]:
    """Collect all unique dates across equity curves."""
    dates: set[str] = set()
    for eq in curves.values():
        for e in eq:
            d = e.get("date", "")
            if d:
                dates.add(d)
    return dates


def _value_at(eq: list[dict], date: str) -> float:
    """Get the equity value at a specific date.

    .. deprecated::
        Retained for backward compatibility; _aggregate_equity now pre-indexes
        curves by date (O(A*B)) instead of calling this O(B) scan per date.

    For dates before the asset's first equity point, the asset's allocated
    capital (its first known equity value) is returned. Returning 0.0 for a
    not-yet-started asset would understate the portfolio's true value and
    corrupt drawdown/return computations when assets have different bar ranges.
    """
    if not eq:
        return 0.0
    first_value = float(eq[0].get("value", 0) or 0)
    for e in eq:
        if e.get("date", "") == date:
            return float(e.get("value", 0) or 0)
    # date not present: walk forward, carrying the last-seen value.
    # For dates preceding the first bar, carry the first value (allocated
    # capital) rather than 0.0.
    prev = first_value
    for e in eq:
        ed = e.get("date", "")
        if ed > date:
            break
        prev = float(e.get("value", 0) or 0)
    return prev


def _correlation_matrix(
    returns_list: list[dict[str, float]],
) -> list[list[float]]:
    """Compute pairwise Pearson correlation between return series.

    Each series is a date→return mapping. Only dates present in both
    series are compared, so assets with mismatched calendars are
    aligned correctly.
    """
    n = len(returns_list)
    if n < 2:
        return [[1.0]]

    matrix = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(1.0)
            else:
                row.append(_date_aligned_pearson(returns_list[i], returns_list[j]))
        matrix.append(row)
    return matrix


def _date_aligned_pearson(xs: dict[str, float], ys: dict[str, float]) -> float:
    """Pearson correlation on the intersection of date keys."""
    common = sorted(set(xs) & set(ys))
    if len(common) < 2:
        return 0.0
    xv = [xs[d] for d in common]
    yv = [ys[d] for d in common]
    return _pearson(xv, yv)
