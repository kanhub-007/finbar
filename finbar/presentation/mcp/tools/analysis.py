"""Analysis MCP tools — indicators and backtesting.

Preferred path: compute_indicators → backtest_strategy_definition (artifact IDs).
For small data: get_cached_prices(tail=N) → apply_indicators → run_backtest.
One-call: run_strategy_pipeline.
"""

import json
import logging
from dataclasses import asdict

from fastmcp import FastMCP

from finbar.core.application.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.startup.service_factory import (
    _get_db,
    _make_apply_indicators_use_case,
    _make_compute_strategy_indicators_use_case,
    _make_get_backtest_equity_use_case,
    _make_get_backtest_summary_use_case,
    _make_get_backtest_trades_use_case,
    _make_list_backtest_results_use_case,
    _make_run_backtest_use_case,
    _make_run_portfolio_backtest_use_case,
    _make_run_strategy_pipeline_use_case,
    _make_store_backtest_result_use_case,
)

from ._shared import _search_filter

logger = logging.getLogger(__name__)


def register_analysis_tools(mcp: FastMCP) -> None:
    """Register indicator and backtest MCP tools."""
    _register_backtest_result_tools(mcp)
    _register_pipeline_tools(mcp)

    @mcp.tool(
        name="apply_indicators",
        description=(
            "Apply technical indicators to OHLCV bars IN-MEMORY. "
            "⚠️ For LARGE datasets (>500 bars), use compute_indicators() "
            "instead — it runs server-side and stores results as reusable "
            "artifacts with artifact IDs, avoiding huge JSON dumps in chat "
            "context.\n\n"
            "Pass bars as JSON string and a list of indicator names "
            '(or a JSON-encoded string like \'["sma_20","rsi_14"]\'). '
            "Returns indicator bars with indicator columns. "
            "Supported indicators: rsi_7, rsi_14, sma_10, sma_20, sma_30, "
            "sma_50, sma_200, ema_12, ema_26, macd, macd_signal, macd_hist, "
            "atr, adx, vwap, bb_upper, bb_middle, bb_lower, ibs, rvol, ker, "
            "kama, price_vs_sma20, trend_direction, trend_strength, "
            "trend_status, swing_high_20, swing_low_20, breakout_level, "
            "breakout_signal, is_power_zone, breakout_quality, "
            "vol_buffer_high, vol_buffer_low, "
            "and proxy indicators (proxy_ibs, proxy_parkinson, "
            "proxy_typical_price, etc.)."
        ),
    )
    def apply_indicators(bars_json: str, indicators: str) -> str:
        """Apply indicators to bars and return enriched JSON.

        Args:
            bars_json: JSON string with OHLCV bars (from get_cached_prices).
            indicators: JSON-encoded list like '["sma_20","rsi_14"]'.

        Returns:
            JSON string with bars plus indicator columns.
        """
        try:
            indicator_list = json.loads(indicators)
            if not isinstance(indicator_list, list):
                return json.dumps({"error": "indicators must be a JSON list"})
        except json.JSONDecodeError:
            return json.dumps({"error": "indicators must be a JSON-encoded list"})

        try:
            bars = json.loads(bars_json)
            if not isinstance(bars, list):
                return json.dumps(
                    {"error": "bars_json must be a JSON array of bar objects"}
                )
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        use_case = _make_apply_indicators_use_case()
        result = use_case.execute(
            ApplyIndicatorsRequest(bars=bars, indicators=indicator_list)
        )

        return json.dumps(
            {
                "bar_count": result.bar_count,
                "indicators_applied": result.indicators_applied,
                "bars": result.bars,
                "error": result.error,
            },
            indent=2,
            default=str,
        )

    @mcp.tool(
        name="list_backtest_strategies",
        description=(
            "List all available strategies that can be used with "
            "run_backtest. Includes both built-in strategies "
            "(sma_crossover, rsi_mean_reversion, momentum_breakout, "
            "auction_drive) and any user-saved JSON strategies. "
            "Returns strategy names, descriptions, required indicators, "
            "and default parameters. "
            "Use the optional search parameter for case-insensitive "
            "name/description matching."
        ),
    )
    def list_backtest_strategies(
        search: str | None = None,
    ) -> str:
        """List all registered backtest strategies, optionally filtered."""
        db = _get_db()
        try:
            use_case = _make_run_backtest_use_case(db)
            strategies = [
                {
                    "name": meta.name,
                    "description": meta.description,
                    "required_indicators": meta.required_indicators,
                    "default_params": meta.params,
                }
                for meta in use_case.list_strategies()
            ]
            error = _search_filter(
                strategies,
                search,
                match_keys=("name", "description"),
                label="strategies",
            )
            if error:
                return error
            return json.dumps(
                {"count": len(strategies), "strategies": strategies},
                indent=2,
            )
        finally:
            db.close()

    @mcp.tool(
        name="run_backtest",
        description=(
            "Run a backtest with a named strategy against historical "
            "OHLCV bars PASSED AS JSON. "
            "⚠️ For EFFICIENT backtests, use the artifact workflow instead: "
            "compute_indicators() → backtest_strategy_definition() with "
            "bars_artifact_id. Or for one-call convenience: "
            "run_strategy_pipeline(). The JSON-in approach here is for "
            "small/quick experiments only.\n\n"
            "Pass bars (optionally enriched with apply_indicators) as a "
            "JSON array, a strategy name (use list_backtest_strategies to "
            "discover available names), and optional strategy parameters "
            "as a JSON object. Works with both built-in strategies "
            "(sma_crossover, rsi_mean_reversion, momentum_breakout, "
            "auction_drive) and saved JSON strategies. "
            "Stores the full result server-side and returns a compact "
            "summary by default with result_id. Use get_backtest_trades() "
            "and get_backtest_equity() to page large details on demand. "
            "Set detail_level='full' only when explicitly "
            "exporting/debugging."
        ),
    )
    def run_backtest(
        bars_json: str,
        strategy_name: str,
        symbol: str = "",
        interval: str = "",
        params_json: str = "{}",
        initial_cash: float = 10000.0,
        leverage: float = 1.0,
        risk_mode: str = "fixed_equity_risk",
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
        cap_explicit_size: bool = True,
        reject_oversized_explicit_orders: bool = False,
        allow_negative_cash: bool = False,
        market_calendar: str = "equity_regular_hours",
        borrow_fee_annual_pct: float = 0.0,
        margin_mode: str = "simplified",
        detail_level: str = "summary",
    ) -> str:
        """Run a backtest and return structured results.

        Args:
            bars_json: JSON string with OHLCV bars (optionally enriched).
            strategy_name: Strategy identifier (e.g. "sma_crossover").
            symbol: Ticker symbol (for result metadata).
            interval: Bar interval (e.g. "1d", "1h").
            params_json: JSON string with strategy parameters.
            initial_cash: Starting capital.
            leverage: Leverage multiplier. 1.0 = spot, 3.0 = 3x.
            risk_mode: fixed_equity_risk or leverage_scaled_risk.
            commission_pct: Percentage commission per side as decimal.
            slippage_pct: Directional slippage percentage as decimal.
            cap_explicit_size: Cap explicit strategy sizes to buying power.
            reject_oversized_explicit_orders: Reject oversized explicit orders.
            allow_negative_cash: Allow cash overdrafts for advanced simulations.
            market_calendar: equity_regular_hours or crypto_24_7.

        Returns:
            JSON string with BacktestResultDTO fields.
        """
        # Parse inputs
        try:
            bars = json.loads(bars_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid bars_json: {e}"})

        try:
            params = json.loads(params_json)
            if not isinstance(params, dict):
                return json.dumps({"error": "params_json must be a JSON object"})
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid params_json: {e}"})

        db = _get_db()
        try:
            use_case = _make_run_backtest_use_case(db)
            result = use_case.execute(
                BacktestRequest(
                    bars=bars,
                    strategy_name=strategy_name,
                    execution=ExecutionConfig(
                        leverage_multiplier=leverage,
                        risk_mode=risk_mode,
                        commission_pct=commission_pct,
                        slippage_pct=slippage_pct,
                        cap_explicit_size=cap_explicit_size,
                        reject_oversized_explicit_orders=(
                            reject_oversized_explicit_orders
                        ),
                        allow_negative_cash=allow_negative_cash,
                        market_calendar=market_calendar,
                        borrow_fee_annual_pct=borrow_fee_annual_pct,
                        margin_mode=margin_mode,
                    ),
                    symbol=symbol,
                    interval=interval,
                    params=params,
                    initial_cash=initial_cash,
                )
            )
            result_dict = _backtest_result_to_dict(result)
            return _store_backtest_response(result_dict, detail_level)
        finally:
            db.close()

    @mcp.tool(
        name="run_portfolio_backtest",
        description=(
            "Run a multi-asset portfolio backtest PASSING BARS AS JSON. "
            "Each asset runs its own strategy with weight-proportional "
            "capital. The portfolio equity curve is the sum of individual "
            "curves. Returns portfolio-level metrics plus per-asset "
            "results and a correlation matrix. "
            "⚠️ Use artifact IDs where possible to avoid large JSON. "
            "Pass portfolio_config_json with "
            '{"assets": [{"symbol":"AAPL","strategy_name":"sma_crossover",'
            '"weight":1.0,"bars":[...]}].'
        ),
    )
    def run_portfolio_backtest(
        portfolio_config_json: str,
        initial_cash: float = 100000.0,
        interval: str = "1d",
        risk_per_trade: float = 0.02,
        leverage: float = 1.0,
        risk_mode: str = "fixed_equity_risk",
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
    ) -> str:
        """Run portfolio backtest from a JSON config string."""
        try:
            config_raw = json.loads(portfolio_config_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid portfolio_config_json: {exc}"})

        from finbar.core.application.dto.portfolio_backtest_request import (
            PortfolioBacktestRequest,
        )
        from finbar.core.domain.entities.portfolio_config import (
            AssetAllocation,
        )

        assets = []
        for item in config_raw.get("assets", []):
            symbol = str(item.get("symbol", ""))
            strategy = str(item.get("strategy_name", ""))
            weight = float(item.get("weight", 1.0))
            bars = item.get("bars", [])
            if not isinstance(bars, list):
                bars = []
            assets.append(
                AssetAllocation(
                    symbol=symbol,
                    strategy_name=strategy,
                    weight=weight,
                    bars=bars,
                )
            )

        if not assets:
            return json.dumps({"error": "No assets specified in portfolio_config_json"})

        use_case = _make_run_portfolio_backtest_use_case()
        request = PortfolioBacktestRequest(
            assets=assets,
            initial_cash=initial_cash,
            interval=interval,
            execution=ExecutionConfig(
                leverage_multiplier=leverage,
                risk_mode=risk_mode,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
            ),
            risk_per_trade=risk_per_trade,
        )
        result = use_case.execute(request)
        return json.dumps(
            {
                "total_return": result.total_return,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "equity_curve": result.equity_curve,
                "correlation_matrix": result.correlation_matrix,
                "error": result.error,
            },
            indent=2,
            default=str,
        )


def _register_backtest_result_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="list_backtest_results",
        description=(
            "List server-side stored backtest results without returning large "
            "trades or equity curves. Optional filters: symbol, strategy_name."
        ),
    )
    def list_backtest_results(
        symbol: str | None = None,
        strategy_name: str | None = None,
        limit: int = 20,
    ) -> str:
        result = _make_list_backtest_results_use_case().execute(
            symbol,
            strategy_name,
            limit,
        )
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="get_backtest_summary",
        description=(
            "Return a compact summary envelope for a stored backtest result. "
            "Use detail_level='sample' for small first/last samples or "
            "detail_level='full' only for explicit export/debug."
        ),
    )
    def get_backtest_summary(result_id: str, detail_level: str = "summary") -> str:
        result = _make_get_backtest_summary_use_case().execute(
            result_id,
            detail_level,
        )
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="get_backtest_trades",
        description=(
            "Return a sorted page of trades for a stored backtest result. "
            "Useful for scalp strategies with thousands of trades."
        ),
    )
    def get_backtest_trades(
        result_id: str,
        page: int = 0,
        page_size: int = 50,
        sort_by: str = "entry_date",
        sort_dir: str = "asc",
    ) -> str:
        result = _make_get_backtest_trades_use_case().execute(
            result_id,
            page,
            page_size,
            sort_by,
            sort_dir,
        )
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="get_backtest_equity",
        description=(
            "Return downsampled or paginated equity points for a stored "
            "backtest result. Modes: none, daily, weekly, drawdown_events, "
            "page, full. Use full only for explicit export/debug."
        ),
    )
    def get_backtest_equity(
        result_id: str,
        mode: str = "daily",
        page: int = 0,
        page_size: int = 500,
    ) -> str:
        result = _make_get_backtest_equity_use_case().execute(
            result_id,
            mode,
            page,
            page_size,
        )
        return json.dumps(asdict(result), indent=2, default=str)


def _register_pipeline_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="compute_strategy_indicators",
        description=(
            "Validate a strategy definition and start indicator computation jobs for "
            "every timeframe (primary + informative) the strategy requires. "
            "Returns job IDs for each timeframe and the list of required "
            "indicators. Poll with get_indicator_job_progress, then use "
            "backtest_strategy_definition with the returned artifact IDs."
        ),
    )
    def compute_strategy_indicators(
        definition_json: str,
        symbol: str,
        source: str = "yfinance",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        result = _make_compute_strategy_indicators_use_case().execute(
            definition_json,
            symbol,
            source,
            params_json={},
            start_date=start_date,
            end_date=end_date,
        )
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="run_strategy_pipeline",
        description=(
            "One-call convenience pipeline: validate strategy, check price "
            "cache, compute required indicators for all timeframes, run "
            "backtest, and return a compact summary with result_id. "
            "Accepts execution controls (initial_cash, risk_per_trade, "
            "leverage, detail_level). "
            "Use this when you want a single call instead of orchestrating "
            "validate → compute → poll → backtest manually."
        ),
    )
    async def run_strategy_pipeline(
        definition_json: str,
        symbol: str,
        source: str = "yfinance",
        start_date: str | None = None,
        end_date: str | None = None,
        initial_cash: float = 10000.0,
        risk_per_trade: float = 0.02,
        leverage: float = 1.0,
        detail_level: str = "summary",
    ) -> str:
        result = await _make_run_strategy_pipeline_use_case().execute(
            definition_json,
            symbol,
            source,
            params_json={},
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            risk_per_trade=risk_per_trade,
            leverage=leverage,
            detail_level=detail_level,
        )
        return json.dumps(asdict(result), indent=2, default=str)


def _store_backtest_response(result: dict, detail_level: str) -> str:
    """Store a full result server-side and return a compact MCP response."""
    stored = _make_store_backtest_result_use_case().execute(result, detail_level)
    return json.dumps(asdict(stored), indent=2, default=str)


def _backtest_result_to_dict(result) -> dict:
    """Serialize a BacktestResultDTO into a plain dictionary."""
    return {
        "strategy_name": result.strategy_name,
        "symbol": result.symbol,
        "interval": result.interval,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "bar_count": result.bar_count,
        "initial_cash": result.initial_cash,
        "final_value": result.final_value,
        "total_return": result.total_return,
        "annualized_return": result.annualized_return,
        "annualization_factor": result.annualization_factor,
        "annualization_warning": result.annualization_warning,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "win_rate": result.win_rate,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "profit_factor": result.profit_factor,
        "calmar_ratio": result.calmar_ratio,
        "total_commission": result.total_commission,
        "total_borrow_cost": result.total_borrow_cost,
        "total_fees": result.total_fees,
        "total_slippage": result.total_slippage,
        "realized_pnl": result.realized_pnl,
        "cash": result.cash,
        "ending_position_size": result.ending_position_size,
        "reconciliation_error": result.reconciliation_error,
        "commission_pct": result.commission_pct,
        "slippage_pct": result.slippage_pct,
        "trust_diagnostics": result.trust_diagnostics,
        "diagnostics": result.diagnostics,
        "analytics": result.analytics,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
        "error": result.error,
    }
