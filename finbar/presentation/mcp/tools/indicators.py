"""MCP tools for Technical Analysis indicators and Trading Metrics."""

import json
from dataclasses import asdict

from fastmcp import FastMCP

from finbar.core.application.dto.start_indicator_job_request import (
    StartIndicatorJobRequest,
)

from ._shared import (
    _make_cancel_indicator_job_use_case,
    _make_delete_artifact_use_case,
    _make_describe_artifact_use_case,
    _make_get_indicator_job_progress_use_case,
    _make_get_indicator_job_results_use_case,
    _make_list_artifacts_use_case,
    _make_query_artifact_bars_use_case,
    _make_start_indicator_job_use_case,
)

# ── TA indicators (all families, 200+ computable indicators) ──
_TA_INDICATORS = [
    # Period-parameterized (dynamic: sma_20, ema_50, rsi_14, atr_10, etc.)
    "sma", "ema", "rsi", "atr", "adx",
    "bb_upper", "bb_middle", "bb_lower",
    # Classic TA (fixed)
    "macd", "macd_signal", "macd_hist", "ker", "kama", "vwap",
    "ibs", "rvol",
    # Trend / Breakout
    "trend_direction", "trend_strength", "trend_status",
    "swing_high_20", "swing_low_20", "breakout_level",
    "breakout_signal", "is_power_zone", "breakout_quality",
    "vol_buffer_high", "vol_buffer_low", "price_vs_sma20",
    # Initial Balance
    "ib_high", "ib_low", "ib_range", "ib_midpoint",
    # AMT — VWAP bands
    "vwap_session", "vwap_upper_1", "vwap_lower_1",
    "vwap_upper_2", "vwap_lower_2",
    # AMT — Volume Profile (session)
    "vp_poc", "vp_vah", "vp_val",
    # AMT — Rolling VP (vp_poc_Nd, vp_vah_Nd, vp_val_Nd for any N)
    "vp_poc_5d", "vp_vah_5d", "vp_val_5d",
    "vp_poc_20d", "vp_vah_20d", "vp_val_20d",
    # AMT — Rolling-window VP (bar-based: rvp_poc_N, etc. for any N)
    "rvp_poc_48", "rvp_vah_48", "rvp_val_48",
    "rvp_poc_96", "rvp_vah_96", "rvp_val_96",
    "rvp_poc_336", "rvp_vah_336", "rvp_val_336",
    # AMT — Composite VP (cvp_poc_Nd, etc. for any N)
    "cvp_poc_5d", "cvp_vah_5d", "cvp_val_5d",
    "cvp_poc_10d", "cvp_vah_10d", "cvp_val_10d",
    "cvp_poc_20d", "cvp_vah_20d", "cvp_val_20d",
    # AMT — Market Profile (TPO)
    "mp_poc", "mp_vah", "mp_val",
    # AMT — State classifiers
    "inside_value", "above_value", "below_value", "at_poc",
    "near_vah", "near_val", "balance_status",
    "distance_to_vah_pct", "distance_to_val_pct", "value_area_width_pct",
    # AMT — Rule signals
    "acceptance_into_value", "rejection_from_edge",
    "acceptance_outside_value", "poc_rejection",
    "edge_volume_building", "value_area_migration",
    # Profile shape classifiers
    "profile_shape", "is_normal_shape", "is_b_shape", "is_p_shape",
    "is_d_shape", "is_neutral_shape",
    # Coil / Squeeze
    "is_coiled", "coil_intensity",
    # Wyckoff phase
    "wyckoff_phase", "poc_slope_5", "poc_slope_20",
    "is_accumulation", "is_markup", "is_distribution",
    "is_markdown", "is_wyckoff_neutral",
    # Spread proxies
    "corwin_schultz_spread", "roll_spread", "abdi_ranaldo_spread",
    "effective_tick_spread", "fong_holden_tran_spread",
    "chung_zhang_spread", "lot_zero_return_spread",
    # Volatility estimators
    "close_to_close_vol", "parkinson_vol", "garman_klass_vol",
    "rogers_satchell_vol", "yang_zhang_vol", "gk_plus_overnight_vol",
    "meilijson_vol", "daily_return_skewness", "daily_return_kurtosis",
    # Intraday realized (requires intraday bars)
    "realized_vol_5m", "realized_vol_15m", "realized_vol_1h",
    "bipower_variation", "realized_skewness", "realized_kurtosis",
    "lee_mykland_jump", "intraday_volume_curve", "empirical_volume_curve",
    # Liquidity / impact
    "amihud_illiq", "amivest_liquidity", "florackis_lambda",
    "hasbrouck_daily_lambda", "liu_illiq", "bao_pan_zhou_cost",
    # Order flow proxies
    "signed_sqrt_volume_ofi", "cumulative_signed_volume_ofi",
    "bvc_buy_volume", "bvc_sell_volume", "bvc_ofi",
    "return_volume_correlation",
    # Informed trading
    "daily_vpin", "spread_based_pin_proxy",
    # Jump / tail risk
    "jump_gap_proxy", "extreme_return_flag",
    "cc_rs_jump_proxy", "overnight_gap_proxy",
    # Resiliency
    "resiliency_autocorr", "resiliency_spread_to_impact",
    "inverse_amihud_resiliency",
    # Intraday seasonality
    "overnight_return", "intraday_return",
    "parametric_u_shape", "first_last_hour_vol_fraction",
    # Order arrival
    "volume_to_trade_count_proxy",
    # Fibonacci
    "fib_382_retrace", "fib_500_retrace", "fib_618_retrace",
    "fib_1618_extension", "fib_confluence_score",
    # Bill Williams
    "awesome_oscillator", "accelerator_oscillator",
    "alligator_jaw", "alligator_teeth", "alligator_lips",
    "alligator_status", "williams_fractal_high", "williams_fractal_low",
    "zone_signal",
    # Trend structure
    "swing_high_n", "swing_low_n", "hh_hl_pattern", "lh_ll_pattern",
    "volume_trend_confirmation", "trend_phase",
    # SMC / Smart Money Concepts
    "bullish_fvg", "bearish_fvg", "bullish_order_block",
    "bearish_order_block", "breaker_block_bullish", "breaker_block_bearish",
    "liquidity_sweep_high", "liquidity_sweep_low",
    "bos", "choch", "premium_discount_zone",
    # VSA signals
    "no_demand", "no_supply", "stopping_volume", "climax_volume",
    "effort_to_rise", "effort_to_fall", "effort_result_divergence",
    "bag_holding", "shakeout", "vsa_test_signal",
    # Supply / demand zones
    "demand_zone_low", "demand_zone_high", "demand_zone_score",
    "supply_zone_low", "supply_zone_high", "supply_zone_score",
    "zone_failure_bullish", "zone_failure_bearish",
    # Hurst / regime
    "hurst_exponent", "fractal_regime", "market_regime",
    "day_type_classification",
    # Derivatives (CoinGlass — crypto only, requires fetch_derivatives)
    "funding_rate", "open_interest",
    "open_interest_delta_1h", "open_interest_delta_24h",
    "cumulative_volume_delta", "long_short_ratio",
    "liquidations_long_1h", "liquidations_short_1h",
    "liquidations_long_24h", "liquidations_short_24h",
    "funding_rate_annualised",
]

# ── Trading Metrics — same catalog as TA (both use the same calculator) ──
_TM_METRICS = _TA_INDICATORS

# ── Proxies (industry-standard, daily-bar substitutes) ──
_PROXIES = [
    "proxy_vwap",
    "proxy_atr",
    "proxy_ibs",
    "proxy_parkinson",
    "proxy_garman_klass",
    "proxy_rogers_satchell",
    "proxy_typical_price",
    "proxy_ohlc4",
    "proxy_iv",
    "proxy_expected_move",
    "proxy_ib_high",
    "proxy_ib_low",
]


def register_indicator_tools(mcp: FastMCP) -> None:
    """Register TA and trading-metrics computation MCP tools."""
    _register_ta_tool(mcp)
    _register_tm_tool(mcp)
    _register_progress_tool(mcp)
    _register_results_tool(mcp)
    _register_artifact_tools(mcp)
    _register_cancel_tool(mcp)


# ═══════════════════════════════════════════════════════════════════════════
# TA Indicators
# ═══════════════════════════════════════════════════════════════════════════


def _register_ta_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="compute_indicators",
        description=_ta_description(),
    )
    async def compute_indicators(
        symbol: str,
        source: str = "yfinance",
        interval: str = "1d",
        indicators_json: str = "[]",
        timeframe_alias: str = "primary",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        return _start_job(
            symbol,
            source,
            interval,
            indicators_json,
            timeframe_alias,
            start_date,
            end_date,
        )


def _ta_description() -> str:
    return (
        "Start a BACKGROUND job to compute Technical Analysis indicators "
        "(SMA, EMA, RSI, MACD, ATR, ADX, Bollinger Bands, Keltner, KAMA, "
        "swing points, trend direction/strength), Auction Market Theory "
        "(AMT) indicators (VWAP SD bands, Volume Profile POC/VAH/VAL, "
        "Market Profile TPO POC/VAH/VAL, "
        "parameterized rolling composites vp_poc_Nd/cvp_poc_Nd/rvp_poc_N for any N, "
        "auction state classifiers, AMT rule signals), "
        "Profile shape & Wyckoff classifiers, Coil/Squeeze, "
        "Spread proxies (Corwin-Schultz, Roll, Abdi-Ranaldo, etc.), "
        "Volatility estimators (Parkinson, Garman-Klass, Yang-Zhang, etc.), "
        "Intraday realized volatility (5m/15m/1h) & bipower variation, "
        "Liquidity/impact (Amihud, Florackis, Hasbrouck, etc.), "
        "Order flow proxies (BVC OFI, signed volume, etc.), "
        "Informed trading (VPIN, PIN proxy), Jump/risk proxies, "
        "Resiliency, Intraday seasonality, "
        "Price action (Fibonacci, Bill Williams, SMC/FVG/order blocks, "
        "VSA signals, Supply/demand zones, Trend structure, Hurst/regime), "
        "Derivatives (funding rate, OI, CVD, liquidations — crypto/CoinGlass) "
        "on cached OHLCV bars. "
        'Pass indicators_json like \'["sma_20","sma_50","rsi_14","atr",'
        '"vp_poc","vp_val","vp_poc_10d","corwin_schultz_spread",'
        '"awesome_oscillator","balance_status"]\'. '
        "Supports arbitrary periods for parameterized indicators. "
        "Full catalog: see get_strategy_capabilities or list_market_metrics. "
        "For multi-timeframe strategies, call once per timeframe.\n\n"
        "AMT indicators work best on intraday data (5min/30min/1h) where "
        "session-scoped profiles produce meaningful distributions. "
        "On daily bars, use rolling composites (vp_poc_Nd) for "
        "multi-day value areas.\n\n"
        "Use start_date/end_date to limit computation to a date range "
        "(e.g., start_date='2026-04-01' processes only recent bars, "
        "not the full history). This is strongly recommended for AI "
        "agents to avoid unnecessary computation. The runner "
        "auto-fetches additional prior bars needed for indicator "
        "warm-up periods (e.g., sma_200 needs 200 bars before start_date).\n\n"
        "Poll with get_indicator_job_progress(job_id), then page results "
        "with get_indicator_job_results(job_id, page, page_size)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Trading Metrics + Proxies
# ═══════════════════════════════════════════════════════════════════════════


def _register_tm_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="compute_trading_metrics",
        description=_tm_description(),
    )
    async def compute_trading_metrics(
        symbol: str,
        source: str = "yfinance",
        interval: str = "1d",
        metrics_json: str = "[]",
        timeframe_alias: str = "primary",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        return _start_job(
            symbol,
            source,
            interval,
            metrics_json,
            timeframe_alias,
            start_date,
            end_date,
        )


def _tm_description() -> str:
    return (
        "Start a BACKGROUND job to compute Trading Metrics, Proxy Metrics, "
        "Market Microstructure metrics, Price Action signals, "
        "and Auction Market Theory (AMT) profile indicators on cached "
        "OHLCV bars.\n\n"
        "Same catalog as compute_indicators — both use the same calculator. "
        "Full catalog: 200+ indicators across 30+ families.\n\n"
        "Trading Metrics: vwap, ibs, rvol, ib_high/low/range/midpoint, "
        "price_vs_sma20, breakout_signal/level/quality, is_power_zone, "
        "vol_buffer_high/low.\n\n"
        "Proxies: proxy_vwap (typical price), proxy_ibs, proxy_atr, "
        "proxy_parkinson, proxy_garman_klass, proxy_rogers_satchell, "
        "proxy_expected_move, proxy_ib_high/low, proxy_iv.\n\n"
        "AMT Profile: vwap_session, vwap_upper_1/2, vwap_lower_1/2, "
        "vp_poc, vp_vah, vp_val (session Volume Profile), "
        "vp_poc_Nd, vp_vah_Nd, vp_val_Nd, rvp_poc_N, cvp_poc_Nd (param.), "
        "mp_poc, mp_vah, mp_val (Market Profile / TPO), "
        "auction state + AMT rule signals.\n\n"
        "Market Microstructure: Spread proxies (7), Volatility estimators (9), "
        "Liquidity/impact (6), Order flow (6), Informed trading (2), "
        "Jump risk (4), Resiliency (3), Intraday seasonality (4), "
        "Intraday realized vol (9).\n\n"
        "Price Action: Fibonacci (5), Bill Williams (9), SMC/FVG/order blocks (11), "
        "VSA signals (10), Supply/demand zones (8), Trend structure (6), "
        "Hurst/regime (4).\n\n"
        "Profile classifiers: profile_shape, Wyckoff phases, coil intensity.\n\n"
        "Derivatives (crypto/CoinGlass): funding rate, OI, CVD, liquidations (11).\n\n"
        "AMT indicators work best on intraday data (5min/30min/1h). "
        "On daily bars, use rolling composites for multi-day value areas.\n\n"
        'Example: metrics_json=["vwap","vp_poc","vp_vah","vp_val",'
        '"inside_value","balance_status","acceptance_outside_value",'
        '"corwin_schultz_spread","awesome_oscillator"]. '
        "See get_strategy_capabilities for full catalog.\n\n"
        "Use start_date/end_date to limit computation to a date range.\n\n"
        "Poll with get_indicator_job_progress(job_id), then page results "
        "with get_indicator_job_results(job_id, page, page_size)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════


def _start_job(
    symbol: str,
    source: str,
    interval: str,
    items_json: str,
    timeframe_alias: str,
    start_date: str | None,
    end_date: str | None,
) -> str:
    try:
        items = json.loads(items_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"}, indent=2)
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        return json.dumps({"error": "Must be a JSON list of strings"}, indent=2)
    request = StartIndicatorJobRequest(
        symbol=symbol.upper(),
        source=source,
        interval=interval,
        mode="selected",
        indicators=items,
        definition=None,
        params={},
        timeframe_alias=timeframe_alias or "primary",
        start_date=start_date,
        end_date=end_date,
    )
    job = _make_start_indicator_job_use_case().execute(request)
    return json.dumps(
        {
            "job_id": job.job_id,
            "status": job.status,
            "symbol": job.symbol,
            "source": job.source,
            "interval": job.interval,
            "timeframe_alias": job.timeframe_alias,
        },
        indent=2,
    )


def _register_progress_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_indicator_job_progress",
        description=(
            "Check an indicator or trading-metrics job's status, progress "
            "percentage, current stage, applied indicators, and error if failed. "
            "The ``failed_indicators`` field lists per-indicator failures as "
            "(name, error) tuples — a metric listed here produced NaN "
            "columns because its handler crashed or its required columns "
            "were missing; inspect it before trusting the output."
        ),
    )
    def get_indicator_job_progress(job_id: str) -> str:
        result = _make_get_indicator_job_progress_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _register_results_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_indicator_job_results",
        description=(
            "Return a page of bars from a completed indicator or trading-metrics "
            "job. Use page/page_size for large datasets. page is zero-based; "
            "page_size defaults to 500 and is capped at 1000."
        ),
    )
    def get_indicator_job_results(
        job_id: str,
        page: int = 0,
        page_size: int = 500,
    ) -> str:
        result = _make_get_indicator_job_results_use_case().execute(
            job_id, page, page_size
        )
        return json.dumps(asdict(result), indent=2, default=str)


def _register_artifact_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="list_artifacts",
        description=(
            "List stored indicator/trading-metric artifacts without returning "
            "bar payloads. Use this to discover reusable enriched datasets "
            "before recomputing indicators. Optional filters: symbol, source, "
            "interval. Returns artifact IDs, date ranges, columns, counts, "
            "and retention metadata."
        ),
    )
    def list_artifacts(
        symbol: str | None = None,
        source: str | None = None,
        interval: str | None = None,
    ) -> str:
        result = _make_list_artifacts_use_case().execute(symbol, source, interval)
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="describe_artifact",
        description=(
            "Describe one artifact without returning bars. Returns metadata, "
            "columns, date range, indicator/feature lists, null counts, and "
            "retention metadata. Use before querying large artifacts."
        ),
    )
    def describe_artifact(artifact_id: str) -> str:
        result = _make_describe_artifact_use_case().execute(artifact_id)
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="query_artifact_bars",
        description=(
            "Return a filtered page of bars from a stored artifact. Supports "
            "column selection via columns_json, date filters, and pagination. "
            "Use this instead of dumping full enriched bar payloads into chat."
        ),
    )
    def query_artifact_bars(
        artifact_id: str,
        columns_json: str = "[]",
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 0,
        page_size: int = 500,
    ) -> str:
        columns = _parse_columns(columns_json)
        if isinstance(columns, dict):
            return json.dumps(columns, indent=2)
        result = _make_query_artifact_bars_use_case().execute(
            artifact_id,
            columns or None,
            start_date,
            end_date,
            page,
            page_size,
        )
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="delete_artifact",
        description=(
            "Explicitly delete a stored indicator/trading-metric artifact by "
            "artifact_id. Artifacts are durable by default and are not deleted "
            "unless this tool is called or an explicit retention policy applies."
        ),
    )
    def delete_artifact(artifact_id: str) -> str:
        result = _make_delete_artifact_use_case().execute(artifact_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _parse_columns(columns_json: str) -> list[str] | dict:
    if not columns_json:
        return []
    try:
        value = json.loads(columns_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid columns_json: {exc}"}
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return {"error": "columns_json must be a JSON list of strings"}
    return value


def _register_cancel_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        name="cancel_indicator_job",
        description="Cancel a queued or running indicator or trading-metrics job.",
    )
    def cancel_indicator_job(job_id: str) -> str:
        result = _make_cancel_indicator_job_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)
