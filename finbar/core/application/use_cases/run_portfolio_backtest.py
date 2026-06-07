"""RunPortfolioBacktestUseCase — execute a multi-asset portfolio backtest."""

import math

from finbar.core.application.dto.portfolio_backtest_request import (
    PortfolioBacktestRequest,
)
from finbar.core.domain.entities.portfolio_result import PortfolioResult
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider


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
        all_returns: dict[str, list[float]] = {}
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
                    borrow_fee_annual_pct=request.execution.borrow_fee_annual_pct,
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


def _compute_returns(eq: list[dict]) -> list[float]:
    """Compute bar-to-bar returns from an equity curve."""
    if len(eq) < 2:
        return []
    returns = []
    for i in range(1, len(eq)):
        prev = eq[i - 1].get("value", 0)
        curr = eq[i].get("value", 0)
        if prev > 0:
            returns.append((curr - prev) / prev)
        else:
            returns.append(0.0)
    return returns


def _aggregate_equity(
    curves: dict[str, list[dict]],
    initial_cash: float,
    interval: str,
    market_calendar: str,
) -> tuple[list[dict], dict]:
    """Sum individual equity curves into a portfolio curve and compute metrics."""
    dates = _all_dates(curves)
    if not dates:
        return [], {}

    portfolio_eq = []
    peak = initial_cash
    for date in sorted(dates):
        total_value = sum(_value_at(curves[sym], date) for sym in curves)
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

    from finbar.infrastructure.services.backtest_result_builder import (
        _annualization_factor,
    )

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
    """Get the equity value at a specific date."""
    for e in eq:
        if e.get("date", "") == date:
            return float(e.get("value", 0) or 0)
    prev = 0.0
    for e in eq:
        ed = e.get("date", "")
        if ed > date:
            break
        prev = float(e.get("value", 0) or 0)
    return prev


def _correlation_matrix(returns_list: list[list[float]]) -> list[list[float]]:
    """Compute pairwise Pearson correlation between return series."""
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
                row.append(_pearson(returns_list[i], returns_list[j]))
        matrix.append(row)
    return matrix


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation between two lists."""
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    xs = xs[:n]
    ys = ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / math.sqrt(vx * vy)
