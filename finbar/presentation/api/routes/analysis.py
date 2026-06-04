"""Analysis API endpoints — indicators and backtesting.

The AI client composes: get_cached_prices → apply_indicators → run_backtest.
"""

import logging

from fastapi import APIRouter, HTTPException

from finbar.core.application.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.presentation.api.dto.requests import (
    ApplyIndicatorsRequest as ApiApplyRequest,
)
from finbar.presentation.api.dto.requests import (
    BacktestRequest as ApiBacktestRequest,
)
from finbar.presentation.api.dto.responses import (
    ApplyIndicatorsResponse,
    BacktestResponse,
    BacktestStrategyResponse,
)
from finbar.presentation.mcp.tools._shared import (
    _make_apply_indicators_use_case,
    _make_run_backtest_use_case,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])


@router.post(
    "/indicators",
    response_model=ApplyIndicatorsResponse,
    summary="Apply technical indicators",
)
def apply_indicators(request: ApiApplyRequest):
    """Apply technical indicators to OHLCV bars.

    Pass raw OHLCV bars and a list of indicator names. Returns enriched
    bars with additional indicator columns.
    """
    use_case = _make_apply_indicators_use_case()
    result = use_case.execute(
        ApplyIndicatorsRequest(
            bars=request.bars,
            indicators=request.indicators,
        )
    )

    if result.error:
        raise HTTPException(status_code=400, detail=result.error)

    return ApplyIndicatorsResponse(
        bar_count=result.bar_count,
        indicators_applied=result.indicators_applied,
        bars=result.bars,
    )


@router.get(
    "/strategies",
    response_model=list[BacktestStrategyResponse],
    summary="List backtest strategies",
)
def list_strategies():
    """List available built-in backtest strategies."""
    use_case = _make_run_backtest_use_case()
    strategies = []
    for name in sorted(use_case._registry):
        strategy = use_case._registry[name]
        meta = strategy.meta()
        strategies.append(
            BacktestStrategyResponse(
                name=meta.name,
                description=meta.description,
                required_indicators=meta.required_indicators,
                default_params=meta.params,
            )
        )
    return strategies


@router.post(
    "/backtest",
    response_model=BacktestResponse,
    summary="Run backtest",
)
def run_backtest(request: ApiBacktestRequest):
    """Run a named strategy against historical bars.

    Pass optionally-enriched OHLCV bars, a strategy name (from
    GET /api/analysis/strategies), and optional parameters.
    Returns performance metrics including Sharpe ratio, drawdown,
    win rate, trade list, and equity curve.
    """
    use_case = _make_run_backtest_use_case()
    result = use_case.execute(
        BacktestRequest(
            bars=request.bars,
            strategy_name=request.strategy_name,
            symbol=request.symbol,
            interval=request.interval,
            params=request.params,
            initial_cash=request.initial_cash,
        )
    )

    if result.error:
        raise HTTPException(status_code=400, detail=result.error)

    return BacktestResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        interval=result.interval,
        start_date=result.start_date,
        end_date=result.end_date,
        bar_count=result.bar_count,
        initial_cash=result.initial_cash,
        final_value=result.final_value,
        total_return=result.total_return,
        annualized_return=result.annualized_return,
        total_trades=result.total_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        win_rate=result.win_rate,
        max_drawdown=result.max_drawdown,
        sharpe_ratio=result.sharpe_ratio,
        sortino_ratio=result.sortino_ratio,
        profit_factor=result.profit_factor,
        calmar_ratio=result.calmar_ratio,
        trades=result.trades,
        equity_curve=result.equity_curve,
    )
