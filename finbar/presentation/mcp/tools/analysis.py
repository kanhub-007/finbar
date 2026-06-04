"""Analysis MCP tools — indicators and backtesting.

The AI client composes: get_cached_prices → apply_indicators → run_backtest.
"""

import json
import logging

from fastmcp import FastMCP

from finbar.core.application.dto.apply_indicators_request import (
    ApplyIndicatorsRequest,
)
from finbar.presentation.mcp.tools._shared import (
    _make_apply_indicators_use_case,
    _make_run_backtest_use_case,
    _resolve_strategy,
)

logger = logging.getLogger(__name__)


def register_analysis_tools(mcp: FastMCP) -> None:
    """Register indicator and backtest MCP tools."""

    @mcp.tool(
        name="apply_indicators",
        description=(
            "Apply technical indicators to OHLCV bars. "
            "Pass bars as JSON string (from get_cached_prices or "
            "fetch_price_history results) and a list of indicator names. "
            "Returns enriched bars with indicator columns. "
            "Supported indicators: rsi_7, rsi_14, sma_10, sma_20, sma_30, "
            "sma_50, sma_200, ema_12, ema_26, macd, macd_signal, macd_hist, "
            "atr, adx, vwap, bb_upper, bb_middle, bb_lower, ibs, rvol, ker, "
            "kama, "
            "price_vs_sma20, trend_direction, trend_strength, trend_status, "
            "swing_high_20, swing_low_20, breakout_level, breakout_signal, "
            "is_power_zone, breakout_quality, vol_buffer_high, vol_buffer_low, "
            "and proxy indicators (proxy_ibs, proxy_parkinson, "
            "proxy_typical_price, etc.)."
        ),
    )
    def apply_indicators(bars_json: str, indicators: list[str]) -> str:
        """Apply indicators to bars and return enriched JSON.

        Args:
            bars_json: JSON string with OHLCV bars (from get_cached_prices).
                       Must include keys: timestamp, open, high, low, close,
                       volume.
            indicators: List of indicator names to compute.

        Returns:
            JSON string with bars plus indicator columns.
        """
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
            ApplyIndicatorsRequest(bars=bars, indicators=indicators)
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
            "List available built-in backtest strategies. "
            "Returns strategy names, descriptions, required indicators, "
            "and default parameters. Use these names in run_backtest()."
        ),
    )
    def list_backtest_strategies() -> str:
        """List all registered backtest strategies and their metadata."""
        use_case = _make_run_backtest_use_case()
        strategies = []
        for name, strategy in sorted(use_case._registry.items()):
            meta = strategy.meta()
            strategies.append(
                {
                    "name": meta.name,
                    "description": meta.description,
                    "required_indicators": meta.required_indicators,
                    "default_params": meta.params,
                }
            )
        return json.dumps(strategies, indent=2)

    @mcp.tool(
        name="run_backtest",
        description=(
            "Run a backtest with a named strategy against historical bars. "
            "Pass bars (optionally enriched with apply_indicators) as JSON, "
            "a strategy name (use list_backtest_strategies to discover), "
            "and optional strategy parameters. "
            "Returns performance metrics: total_return, sharpe_ratio, "
            "max_drawdown, win_rate, trades list, equity_curve. "
            "Built-in strategies: sma_crossover, rsi_mean_reversion."
        ),
    )
    def run_backtest(
        bars_json: str,
        strategy_name: str,
        symbol: str = "",
        interval: str = "",
        params_json: str = "{}",
        initial_cash: float = 10000.0,
    ) -> str:
        """Run a backtest and return structured results.

        Args:
            bars_json: JSON string with OHLCV bars (optionally enriched).
            strategy_name: Strategy identifier (e.g. "sma_crossover").
            symbol: Ticker symbol (for result metadata).
            interval: Bar interval (e.g. "1d", "1h").
            params_json: JSON string with strategy parameters.
            initial_cash: Starting capital.

        Returns:
            JSON string with BacktestResultDTO fields.
        """
        # Parse inputs
        try:
            bars = json.loads(bars_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid bars_json: {e}"})

        try:
            json.loads(params_json)  # validate only
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid params_json: {e}"})

        strategy = _resolve_strategy(strategy_name)
        if strategy is None:
            return json.dumps({"error": f"Unknown strategy '{strategy_name}'"})

        # Run backtest directly with the resolved strategy
        df = _bars_to_df(bars)
        if df.empty:
            return json.dumps({"error": "No bars to process"})

        from finbar.infrastructure.services.backtest_runner import BacktestRunner

        runner = BacktestRunner()
        raw = runner.run(df, strategy, initial_cash)
        raw["symbol"] = symbol
        raw["interval"] = interval

        return json.dumps(
            {
                "strategy_name": raw.get("strategy_name", ""),
                "symbol": raw.get("symbol", ""),
                "interval": raw.get("interval", ""),
                "start_date": raw.get("start_date", ""),
                "end_date": raw.get("end_date", ""),
                "bar_count": raw.get("bar_count", 0),
                "initial_cash": raw.get("initial_cash", 0),
                "final_value": raw.get("final_value", 0),
                "total_return": raw.get("total_return", 0),
                "annualized_return": raw.get("annualized_return"),
                "total_trades": raw.get("total_trades", 0),
                "winning_trades": raw.get("winning_trades", 0),
                "losing_trades": raw.get("losing_trades", 0),
                "win_rate": raw.get("win_rate", 0),
                "max_drawdown": raw.get("max_drawdown", 0),
                "sharpe_ratio": raw.get("sharpe_ratio", 0),
                "sortino_ratio": raw.get("sortino_ratio", 0),
                "profit_factor": raw.get("profit_factor"),
                "calmar_ratio": raw.get("calmar_ratio", 0),
                "trades": raw.get("trades", []),
                "equity_curve": raw.get("equity_curve", []),
                "error": raw.get("error"),
            },
            indent=2,
            default=str,
        )

    @mcp.tool(
        name="merge_and_backtest",
        description=(
            "Run a multi-interval backtest by merging primary (intraday) "
            "and informative (daily) bars before running the strategy. "
            "For strategies like auction_drive that need intraday entries "
            "plus daily trend context. Merges columns with interval "
            "suffix (e.g., sma_50 → sma_50_1d). Applies required "
            "indicators automatically."
        ),
    )
    def merge_and_backtest(
        primary_bars_json: str,
        informative_bars_json: str,
        strategy_name: str,
        informative_interval: str = "1d",
        symbol: str = "",
        interval: str = "",
        initial_cash: float = 10000.0,
    ) -> str:
        try:
            primary_bars = json.loads(primary_bars_json)
            info_bars = json.loads(informative_bars_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        primary_df = _bars_to_df(primary_bars)
        info_df = _bars_to_df(info_bars)

        if primary_df.empty:
            return json.dumps({"error": "Primary bars list is empty"})

        from finbar.infrastructure.services.bar_merger import merge_timeframes

        merged_df = merge_timeframes(primary_df, info_df, informative_interval)

        strategy = _resolve_strategy(strategy_name)
        if strategy is None:
            return json.dumps({"error": f"Unknown strategy '{strategy_name}'"})

        required = strategy.meta().required_indicators
        if required:
            uc = _make_apply_indicators_use_case()
            merged_df = uc._calculator.calculate(merged_df, required)

        from finbar.infrastructure.services.backtest_runner import BacktestRunner

        runner = BacktestRunner()
        raw = runner.run(merged_df, strategy, initial_cash)
        raw["symbol"] = symbol
        raw["interval"] = interval

        return json.dumps(
            {
                "strategy_name": raw.get("strategy_name", ""),
                "symbol": raw.get("symbol", ""),
                "interval": raw.get("interval", ""),
                "start_date": raw.get("start_date", ""),
                "end_date": raw.get("end_date", ""),
                "bar_count": raw.get("bar_count", 0),
                "initial_cash": raw.get("initial_cash", 0),
                "final_value": raw.get("final_value", 0),
                "total_return": raw.get("total_return", 0),
                "annualized_return": raw.get("annualized_return"),
                "total_trades": raw.get("total_trades", 0),
                "winning_trades": raw.get("winning_trades", 0),
                "losing_trades": raw.get("losing_trades", 0),
                "win_rate": raw.get("win_rate", 0),
                "max_drawdown": raw.get("max_drawdown", 0),
                "sharpe_ratio": raw.get("sharpe_ratio", 0),
                "sortino_ratio": raw.get("sortino_ratio", 0),
                "profit_factor": raw.get("profit_factor"),
                "calmar_ratio": raw.get("calmar_ratio", 0),
                "trades": raw.get("trades", []),
                "equity_curve": raw.get("equity_curve", []),
                "error": raw.get("error"),
            },
            indent=2,
            default=str,
        )


def _bars_to_df(bars: list[dict]):
    """Convert a list of bar dicts to a pandas DataFrame with datetime index."""
    import pandas as pd

    df = pd.DataFrame(bars)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
    return df
