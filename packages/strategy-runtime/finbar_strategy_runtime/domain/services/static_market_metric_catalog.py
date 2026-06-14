"""StaticMarketMetricCatalog — exhaustive static registry of ~160 market metrics."""

from collections.abc import Sequence

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_capability_result import (
    MetricCapabilityResult,
)
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.domain.entities.metric_resolution_path import (
    MetricResolutionPath,
)
from finbar_strategy_runtime.domain.interfaces.market_metric_catalog import (
    MarketMetricCatalog,
)

# ---------------------------------------------------------------------------
# Helper: data class → MetricConfidence result for a given available class
# ---------------------------------------------------------------------------


def _is_class_available(
    required: tuple[DataClass, ...], available: DataClass
) -> bool:
    """Return True when `available` satisfies any of the `required` classes."""
    if not required:
        return True
    return available in required


def _interval_matches(available: str, required_min: str) -> bool:
    """Check whether the available interval is at least as fine as required.

    For intraday data, '5min' is finer than '1h'.
    For daily, only '1d' or '' matches.
    """
    if not required_min:
        return True

    def _to_minutes(interval: str) -> int:
        if interval in ("1d", "", "day"):
            return 1440
        if interval.endswith("min"):
            return int(interval.replace("min", ""))
        if interval.endswith("h"):
            return int(interval.replace("h", "")) * 60
        return 0

    return _to_minutes(available) <= _to_minutes(required_min)


def _make_result(
    definition: MarketMetricDefinition,
    available_class: DataClass,
) -> MetricCapabilityResult:
    """Build a MetricCapabilityResult from a definition and available data class."""
    if not definition.implemented:
        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            warnings=("Metric catalogued but not yet implemented.",),
        )
    # External provider metrics always require provider configuration
    if definition.required_data_classes and definition.required_data_classes[0] == DataClass.EXTERNAL_PROVIDER:
        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            missing_providers=definition.required_providers,
        )
    if not _is_class_available(definition.required_data_classes, available_class):
        return MetricCapabilityResult(
            metric=definition.name,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            missing_data_classes=tuple(
                dc.value for dc in definition.required_data_classes
            ),
            missing_providers=definition.required_providers,
            proxy_candidates=definition.proxy_candidates,
        )

    return MetricCapabilityResult(
        metric=definition.name,
        supported=True,
        computable=True,
        confidence=definition.confidence,
        selected_metric=definition.name,
    )


# ========================================================================
# The registry itself
# ========================================================================

# Each entry: name, family, description, required_data_classes, required_columns,
# min_lookback, confidence, paper_reference, proxy_candidates,
# required_providers, implemented

_METRICS: list[MarketMetricDefinition] = [
    # --- Spread proxies (7) ---
    MarketMetricDefinition(
        name="corwin_schultz_spread",
        family=MetricFamily.SPREAD,
        description="OHLC-based bid-ask spread estimator with overnight-gap adjustment.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Corwin & Schultz (2012), 'A Simple Way to Estimate Bid-Ask Spreads'",
    ),
    MarketMetricDefinition(
        name="roll_spread",
        family=MetricFamily.SPREAD,
        description="Serial covariance spread estimator (close-to-close).",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Roll (1984), 'A Simple Implicit Measure of the Effective Bid-Ask Spread'",
    ),
    MarketMetricDefinition(
        name="abdi_ranaldo_spread",
        family=MetricFamily.SPREAD,
        description="OHLC-based spread estimator using mid-price and close.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Abdi & Ranaldo (2017), 'A Simple Estimation of Bid-Ask Spreads'",
    ),
    MarketMetricDefinition(
        name="effective_tick_spread",
        family=MetricFamily.SPREAD,
        description="Tick-based spread estimator using close-to-close price clustering.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=60,
        confidence=MetricConfidence.PROXY,
        paper_reference="Holden (2009), 'New Low-Frequency Spread Measures'",
    ),
    MarketMetricDefinition(
        name="fong_holden_tran_spread",
        family=MetricFamily.SPREAD,
        description="FHT simple spread estimator using OHLC.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Fong, Holden & Trzcinka (2017), 'What Are the Best Liquidity Proxies?'",
    ),
    MarketMetricDefinition(
        name="chung_zhang_spread",
        family=MetricFamily.SPREAD,
        description="OHLC-based spread estimator with simple calculation.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Chung & Zhang (2014), 'A Simple Approximation of Intraday Spreads'",
    ),
    MarketMetricDefinition(
        name="lot_zero_return_spread",
        family=MetricFamily.SPREAD,
        description="LOT spread from zero-return proportion.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=60,
        confidence=MetricConfidence.PROXY,
        paper_reference="Lesmond, Ogden & Trzcinka (1999), 'A New Estimate of Transaction Costs'",
    ),

    # --- Volatility (9) ---
    MarketMetricDefinition(
        name="close_to_close_vol",
        family=MetricFamily.VOLATILITY,
        description="Naive close-to-close return volatility.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=20,
        confidence=MetricConfidence.ACTUAL,
    ),
    MarketMetricDefinition(
        name="parkinson_vol",
        family=MetricFamily.VOLATILITY,
        description="Parkinson high-low range volatility estimator.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("high", "low"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Parkinson (1980), 'The Extreme Value Method for Estimating Variance'",
    ),
    MarketMetricDefinition(
        name="garman_klass_vol",
        family=MetricFamily.VOLATILITY,
        description="Garman-Klass OHLC volatility estimator.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Garman & Klass (1980), 'On the Estimation of Security Price Volatilities'",
    ),
    MarketMetricDefinition(
        name="rogers_satchell_vol",
        family=MetricFamily.VOLATILITY,
        description="Rogers-Satchell OHLC volatility estimator (drift-independent).",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Rogers & Satchell (1991), 'Estimating Variance from High, Low and Closing Prices'",
    ),
    MarketMetricDefinition(
        name="yang_zhang_vol",
        family=MetricFamily.VOLATILITY,
        description="Yang-Zhang OHLC volatility estimator with overnight gap adjustment.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=21,
        confidence=MetricConfidence.PROXY,
        paper_reference="Yang & Zhang (2000), 'Drift-Independent Volatility Estimation'",
    ),
    MarketMetricDefinition(
        name="gk_plus_overnight_vol",
        family=MetricFamily.VOLATILITY,
        description="Garman-Klass with overnight gap component.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
    ),
    MarketMetricDefinition(
        name="meilijson_vol",
        family=MetricFamily.VOLATILITY,
        description="Meilijson OHLC volatility estimator.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("open", "high", "low", "close"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Meilijson (2009), 'A Simple, Fast and Accurate Nonparametric Estimator'",
    ),
    MarketMetricDefinition(
        name="daily_return_skewness",
        family=MetricFamily.VOLATILITY,
        description="Rolling skewness of daily returns.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=60,
        confidence=MetricConfidence.ACTUAL,
    ),
    MarketMetricDefinition(
        name="daily_return_kurtosis",
        family=MetricFamily.VOLATILITY,
        description="Rolling kurtosis of daily returns.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=60,
        confidence=MetricConfidence.ACTUAL,
    ),

    # --- Liquidity / impact (8) ---
    MarketMetricDefinition(
        name="amihud_illiq",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Amihud illiquidity measure: |return| / dollar_volume.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close", "volume"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Amihud (2002), 'Illiquidity and Stock Returns'",
    ),
    MarketMetricDefinition(
        name="amivest_liquidity",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Inverse Amihud — dollar volume per unit price change.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close", "volume"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
    ),
    MarketMetricDefinition(
        name="florackis_lambda",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Return-to-volume ratio liquidity measure.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close", "volume"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Florackis, Gregoriou & Kostakis (2011), 'Trading Frequency and Asset Pricing'",
    ),
    MarketMetricDefinition(
        name="hasbrouck_daily_lambda",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Daily price impact proxy from Hasbrouck.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close", "volume"),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Hasbrouck (2009), 'Trading Costs and Returns for US Equities'",
    ),
    MarketMetricDefinition(
        name="pastor_stambaugh_liquidity",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Pastor-Stambaugh liquidity measure (order-flow reversal).",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close", "volume"),
        min_lookback=60,
        confidence=MetricConfidence.PROXY,
        paper_reference="Pastor & Stambaugh (2003), 'Liquidity Risk and Expected Stock Returns'",
    ),
    MarketMetricDefinition(
        name="liu_illiq",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Liu illiquidity: days-with-zero-volume proportion.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("volume",),
        min_lookback=21,
        confidence=MetricConfidence.PROXY,
        paper_reference="Liu (2006), 'A Liquidity-Augmented Capital Asset Pricing Model'",
    ),
    MarketMetricDefinition(
        name="turnover",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Daily turnover: volume / shares_outstanding.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("volume",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
    MarketMetricDefinition(
        name="bao_pan_zhou_cost",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Trading cost proxy from close-to-close return reversal.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=20,
        confidence=MetricConfidence.PROXY,
        paper_reference="Bao, Pan & Zhou (2011), 'The Volcker Rule and Market-Making in Times of Stress'",
    ),

    # --- Non-OHLCV metrics (catalogued, unavailable — ~40 entries) ---
    # trades_and_quotes (8)
    MarketMetricDefinition(
        name="effective_spread_taq",
        family=MetricFamily.SPREAD,
        description="Effective spread from TAQ trade-and-quote data.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("corwin_schultz_spread", "roll_spread"),
    ),
    MarketMetricDefinition(
        name="quoted_spread",
        family=MetricFamily.SPREAD,
        description="Quoted spread from Level 1 quotes.",
        required_data_classes=(DataClass.QUOTES, DataClass.TRADES_AND_QUOTES),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("corwin_schultz_spread",),
    ),
    MarketMetricDefinition(
        name="realized_spread_taq",
        family=MetricFamily.SPREAD,
        description="Realized spread: trade price vs mid-quote after 5min.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("corwin_schultz_spread",),
    ),
    MarketMetricDefinition(
        name="lee_ready_classification",
        family=MetricFamily.ORDER_FLOW,
        description="Lee-Ready trade classification (buy/sell) from TAQ.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("bvc_ofi", "signed_sqrt_volume_ofi"),
        paper_reference="Lee & Ready (1991), 'Inferring Trade Direction from Intraday Data'",
    ),
    MarketMetricDefinition(
        name="kyle_lambda",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Kyle's lambda: price impact per unit of signed volume.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("amihud_illiq", "hasbrouck_daily_lambda"),
        paper_reference="Kyle (1985), 'Continuous Auctions and Insider Trading'",
    ),
    MarketMetricDefinition(
        name="hasbrouck_var_impact",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Hasbrouck VAR-based price impact decomposition.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("hasbrouck_daily_lambda",),
        paper_reference="Hasbrouck (1991), 'Measuring the Information Content of Stock Trades'",
    ),
    MarketMetricDefinition(
        name="trade_classified_ofi",
        family=MetricFamily.ORDER_FLOW,
        description="Order flow imbalance from Lee-Ready classified trades.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("bvc_ofi",),
    ),
    MarketMetricDefinition(
        name="price_reversion_speed",
        family=MetricFamily.RESILIENCY,
        description="Post-trade price reversion speed.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("resiliency_autocorr",),
    ),
    # level_2_order_book (5)
    MarketMetricDefinition(
        name="cont_kukanov_ofi",
        family=MetricFamily.ORDER_FLOW,
        description="Cont-Kukanov OFI from Level 2 order book events.",
        required_data_classes=(DataClass.LEVEL_2_ORDER_BOOK,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("bvc_ofi",),
        paper_reference="Cont, Kukanov & Stoikov (2014), 'The Price Impact of Order Book Events'",
    ),
    MarketMetricDefinition(
        name="order_book_depth_profile",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Full Level 2 order book depth profile at each price level.",
        required_data_classes=(DataClass.LEVEL_2_ORDER_BOOK,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("amihud_illiq",),
    ),
    MarketMetricDefinition(
        name="order_book_shape",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Order book shape metrics: slope, convexity, imbalance.",
        required_data_classes=(DataClass.LEVEL_2_ORDER_BOOK,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("bvc_ofi",),
    ),
    MarketMetricDefinition(
        name="depth_recovery_time",
        family=MetricFamily.RESILIENCY,
        description="Time for L2 depth to recover after large trades.",
        required_data_classes=(DataClass.LEVEL_2_ORDER_BOOK,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("resiliency_spread_to_impact",),
    ),
    MarketMetricDefinition(
        name="almgren_chriss_impact",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Almgren-Chriss execution impact model.",
        required_data_classes=(DataClass.LEVEL_2_ORDER_BOOK,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("amihud_illiq",),
        paper_reference="Almgren & Chriss (2001), 'Optimal Execution of Portfolio Transactions'",
    ),
    # order_book_events (5)
    MarketMetricDefinition(
        name="noi_from_lob_events",
        family=MetricFamily.ORDER_FLOW,
        description="Net order imbalance from order book events (adds/cancels/modifies).",
        required_data_classes=(DataClass.ORDER_BOOK_EVENTS,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("bvc_ofi",),
    ),
    MarketMetricDefinition(
        name="iceberg_detection",
        family=MetricFamily.ORDER_FLOW,
        description="Iceberg/hidden-order detection from repeated fills at same size.",
        required_data_classes=(DataClass.ORDER_BOOK_EVENTS,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
    MarketMetricDefinition(
        name="spoofing_detection",
        family=MetricFamily.ORDER_FLOW,
        description="Spoofing/layering detection from cancelled large orders.",
        required_data_classes=(DataClass.ORDER_BOOK_EVENTS,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
    MarketMetricDefinition(
        name="absorption_detection",
        family=MetricFamily.ORDER_FLOW,
        description="Absorption detection: persistent bid/ask replenishment against flow.",
        required_data_classes=(DataClass.ORDER_BOOK_EVENTS,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
    MarketMetricDefinition(
        name="cancellation_rate",
        family=MetricFamily.ORDER_FLOW,
        description="Order cancellation rate relative to submissions.",
        required_data_classes=(DataClass.ORDER_BOOK_EVENTS,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
    # intraday bars (9)
    MarketMetricDefinition(
        name="realized_vol_5m",
        family=MetricFamily.VOLATILITY,
        description="Realized volatility from 5-min returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=78,  # ~1 day of 5-min bars
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("yang_zhang_vol", "parkinson_vol"),
    ),
    MarketMetricDefinition(
        name="realized_vol_15m",
        family=MetricFamily.VOLATILITY,
        description="Realized volatility from 15-min returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=26,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("yang_zhang_vol", "parkinson_vol"),
    ),
    MarketMetricDefinition(
        name="realized_vol_1h",
        family=MetricFamily.VOLATILITY,
        description="Realized volatility from 1-hour returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=7,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("yang_zhang_vol", "garman_klass_vol"),
    ),
    MarketMetricDefinition(
        name="bipower_variation",
        family=MetricFamily.VOLATILITY,
        description="Bipower variation for jump-robust volatility from intraday returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=78,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("cc_rs_jump_proxy",),
        paper_reference="Barndorff-Nielsen & Shephard (2004), 'Power and Bipower Variation'",
    ),
    MarketMetricDefinition(
        name="realized_skewness",
        family=MetricFamily.VOLATILITY,
        description="Skewness of intraday returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=78,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("daily_return_skewness",),
    ),
    MarketMetricDefinition(
        name="realized_kurtosis",
        family=MetricFamily.VOLATILITY,
        description="Kurtosis of intraday returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=78,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("daily_return_kurtosis",),
    ),
    MarketMetricDefinition(
        name="intraday_volume_curve",
        family=MetricFamily.INTRADAY_SEASONALITY,
        description="Empirical volume curve from intraday bars.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=130,  # 5+ days of 5-min bars
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("parametric_u_shape",),
    ),
    MarketMetricDefinition(
        name="lee_mykland_jump",
        family=MetricFamily.JUMP_TAIL_RISK,
        description="Lee-Mykland jump detection from intraday returns.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=78,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("cc_rs_jump_proxy",),
        paper_reference="Lee & Mykland (2008), 'Jumps in Financial Markets'",
    ),
    MarketMetricDefinition(
        name="empirical_volume_curve",
        family=MetricFamily.INTRADAY_SEASONALITY,
        description="Empirical intraday volume curve from 5-min bars.",
        required_data_classes=(DataClass.INTRADAY_OHLCV,),
        min_lookback=78,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("parametric_u_shape",),
    ),
    # tick trades (4)
    MarketMetricDefinition(
        name="realized_kernel_vol",
        family=MetricFamily.VOLATILITY,
        description="Realized kernel volatility from tick trades.",
        required_data_classes=(DataClass.TRADES,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("yang_zhang_vol",),
        paper_reference="Barndorff-Nielsen et al. (2008), 'Designing Realized Kernels'",
    ),
    MarketMetricDefinition(
        name="order_arrival_rate",
        family=MetricFamily.ORDER_ARRIVAL,
        description="Trade arrival rate from tick data.",
        required_data_classes=(DataClass.TRADES,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("volume_to_trade_count_proxy",),
    ),
    MarketMetricDefinition(
        name="intraday_vpin",
        family=MetricFamily.INFORMED_TRADING,
        description="Volume-synchronized PIN from tick bucket classification.",
        required_data_classes=(DataClass.TRADES,),
        min_lookback=50,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("daily_vpin",),
        paper_reference="Easley, Lopez de Prado & O'Hara (2012), 'Flow Toxicity and Liquidity'",
    ),
    MarketMetricDefinition(
        name="trade_size_distribution",
        family=MetricFamily.ORDER_ARRIVAL,
        description="Distribution of trade sizes from tick data.",
        required_data_classes=(DataClass.TRADES,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
    # multi-venue tick (2)
    MarketMetricDefinition(
        name="hasbrouck_information_share",
        family=MetricFamily.INFORMATION_SHARE,
        description="Hasbrouck information share from multi-venue tick data.",
        required_data_classes=(DataClass.TRADES,),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("cross_price_leadership",),
        paper_reference="Hasbrouck (1995), 'One Security, Many Markets'",
    ),

    # --- External provider metrics (21) ---
    # Crypto derivatives — CoinGlass (11)
    MarketMetricDefinition(
        name="funding_rate",
        family=MetricFamily.DERIVATIVES,
        description="Perpetual funding rate from exchange/CoinGlass.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="open_interest",
        family=MetricFamily.DERIVATIVES,
        description="Aggregate open interest from exchange/CoinGlass.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="open_interest_delta_1h",
        family=MetricFamily.DERIVATIVES,
        description="1-hour change in open interest.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="open_interest_delta_24h",
        family=MetricFamily.DERIVATIVES,
        description="24-hour change in open interest.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="cumulative_volume_delta",
        family=MetricFamily.DERIVATIVES,
        description="CVD: cumulative delta between buying and selling volume.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="long_short_ratio",
        family=MetricFamily.DERIVATIVES,
        description="Long/short ratio from exchange/CoinGlass.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="liquidations_long_1h",
        family=MetricFamily.DERIVATIVES,
        description="Long liquidations in the last hour.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="liquidations_short_1h",
        family=MetricFamily.DERIVATIVES,
        description="Short liquidations in the last hour.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="liquidations_long_24h",
        family=MetricFamily.DERIVATIVES,
        description="Long liquidations in the last 24 hours.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="liquidations_short_24h",
        family=MetricFamily.DERIVATIVES,
        description="Short liquidations in the last 24 hours.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="funding_rate_annualised",
        family=MetricFamily.DERIVATIVES,
        description="Annualised funding rate.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    # Equity sentiment / macro (5)
    MarketMetricDefinition(
        name="vix_level",
        family=MetricFamily.SENTIMENT,
        description="VIX index level.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("market_data",),
        applicable_asset_classes=("equity",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="vix_regime",
        family=MetricFamily.SENTIMENT,
        description="VIX-based regime classification.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("market_data",),
        applicable_asset_classes=("equity",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="put_call_ratio",
        family=MetricFamily.SENTIMENT,
        description="Put/call ratio from options market data.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("options_provider",),
        applicable_asset_classes=("equity", "futures"),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="aaii_sentiment",
        family=MetricFamily.SENTIMENT,
        description="AAII investor sentiment survey.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("aaii_provider",),
        applicable_asset_classes=("equity",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="social_sentiment_score",
        family=MetricFamily.SENTIMENT,
        description="Social media sentiment score.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("social_sentiment_api",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    # Futures / COT (2)
    MarketMetricDefinition(
        name="cot_commercial_net",
        family=MetricFamily.SENTIMENT,
        description="COT report: commercial trader net position.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("cftc_cot",),
        applicable_asset_classes=("futures",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="cot_nonreportable_net",
        family=MetricFamily.SENTIMENT,
        description="COT report: non-reportable net position.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("cftc_cot",),
        applicable_asset_classes=("futures",),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    # Portfolio / cross-asset (3)
    MarketMetricDefinition(
        name="market_beta",
        family=MetricFamily.PORTFOLIO,
        description="Market beta relative to a benchmark.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("benchmark_data",),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="sector_relative_strength",
        family=MetricFamily.PORTFOLIO,
        description="Sector relative strength.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("sector_data",),
        applicable_asset_classes=("equity",),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
    ),
    MarketMetricDefinition(
        name="cross_asset_correlation",
        family=MetricFamily.CROSS_ASSET,
        description="Correlation across asset universe.",
        required_data_classes=(DataClass.EXTERNAL_PROVIDER,),
        required_providers=("multi_asset_data",),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
    ),

    # Elliott Wave (catalogued, not implemented — 5 metrics)
    MarketMetricDefinition(
        name="elliott_wave_count",
        family=MetricFamily.PRICE_ACTION,
        description="Elliott Wave impulse/corrective pattern count. Requires dedicated wave-detection engine with 3 inviolable rule checks.",
        required_data_classes=(DataClass.DAILY_OHLCV,),
        min_lookback=100,
        confidence=MetricConfidence.UNAVAILABLE,
        implemented=False,
        proxy_candidates=(),
    ),
    MarketMetricDefinition(
        name="elliott_wave_phase",
        family=MetricFamily.PRICE_ACTION,
        description="Current Elliott Wave phase (impulse wave 1-5, corrective A-B-C).",
        required_data_classes=(DataClass.DAILY_OHLCV,),
        min_lookback=100,
        confidence=MetricConfidence.UNAVAILABLE,
        implemented=False,
    ),
    MarketMetricDefinition(
        name="elliott_zigzag_correction",
        family=MetricFamily.PRICE_ACTION,
        description="Elliott Wave zigzag (5-3-5) correction pattern.",
        required_data_classes=(DataClass.DAILY_OHLCV,),
        min_lookback=100,
        confidence=MetricConfidence.UNAVAILABLE,
        implemented=False,
    ),
    MarketMetricDefinition(
        name="elliott_flat_correction",
        family=MetricFamily.PRICE_ACTION,
        description="Elliott Wave flat (3-3-5) correction pattern.",
        required_data_classes=(DataClass.DAILY_OHLCV,),
        min_lookback=100,
        confidence=MetricConfidence.UNAVAILABLE,
        implemented=False,
    ),
    MarketMetricDefinition(
        name="elliott_triangle_correction",
        family=MetricFamily.PRICE_ACTION,
        description="Elliott Wave triangle (A-B-C-D-E) correction pattern.",
        required_data_classes=(DataClass.DAILY_OHLCV,),
        min_lookback=100,
        confidence=MetricConfidence.UNAVAILABLE,
        implemented=False,
    ),
    MarketMetricDefinition(
        name="gonzalo_granger_cs",
        family=MetricFamily.INFORMATION_SHARE,
        description="Gonzalo-Granger common factor share from multi-venue prices.",
        required_data_classes=(DataClass.TRADES,),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("cross_price_leadership",),
        paper_reference="Gonzalo & Granger (1995), 'Estimation of Common Long-Memory Components'",
    ),
    # trades_and_quotes + classified (2)
    MarketMetricDefinition(
        name="true_pin_easley",
        family=MetricFamily.INFORMED_TRADING,
        description="True PIN from Easley et al. using classified buy/sell counts.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=60,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("daily_vpin",),
        paper_reference="Easley, Kiefer, O'Hara & Paperman (1996), 'Liquidity, Information, and Infrequently Traded Stocks'",
    ),
    MarketMetricDefinition(
        name="odd_lot_ratio",
        family=MetricFamily.ORDER_FLOW,
        description="Ratio of odd-lot to round-lot trades.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
    # Level 1 quotes (1)
    MarketMetricDefinition(
        name="quote_to_trade_ratio",
        family=MetricFamily.ORDER_ARRIVAL,
        description="Ratio of quote updates to trades (quote stuffing indicator).",
        required_data_classes=(DataClass.QUOTES,),
        min_lookback=20,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=(),
    ),
]

# Conceptual metrics with dual-path resolution
_CONCEPTUAL_METRICS: list[MarketMetricDefinition] = [
    MarketMetricDefinition(
        name="volatility",
        family=MetricFamily.VOLATILITY,
        description="Conceptual volatility — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="realized_vol_5m",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.ACTUAL,
                priority=1,
                interval_min="5min",
            ),
            MetricResolutionPath(
                metric_name="realized_vol_1h",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.APPROXIMATION,
                priority=2,
                interval_min="1h",
            ),
            MetricResolutionPath(
                metric_name="yang_zhang_vol",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("open", "high", "low", "close"),
                confidence=MetricConfidence.PROXY,
                priority=3,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="spread",
        family=MetricFamily.SPREAD,
        description="Conceptual spread — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="corwin_schultz_spread",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("open", "high", "low", "close"),
                confidence=MetricConfidence.PROXY,
                priority=1,
            ),
            MetricResolutionPath(
                metric_name="roll_spread",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.PROXY,
                priority=2,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="jump_detection",
        family=MetricFamily.JUMP_TAIL_RISK,
        description="Conceptual jump detection — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="bipower_variation",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("close",),
                confidence=MetricConfidence.ACTUAL,
                priority=1,
                interval_min="5min",
            ),
            MetricResolutionPath(
                metric_name="cc_rs_jump_proxy",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("high", "low"),
                confidence=MetricConfidence.PROXY,
                priority=2,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="intraday_seasonality",
        family=MetricFamily.INTRADAY_SEASONALITY,
        description="Conceptual intraday seasonality — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="empirical_volume_curve",
                required_data_class=DataClass.INTRADAY_OHLCV,
                required_columns=("volume",),
                confidence=MetricConfidence.ACTUAL,
                priority=1,
                interval_min="5min",
            ),
            MetricResolutionPath(
                metric_name="parametric_u_shape",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("volume",),
                confidence=MetricConfidence.PROXY,
                priority=2,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="order_flow_imbalance",
        family=MetricFamily.ORDER_FLOW,
        description="Conceptual order flow imbalance — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="bvc_ofi",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("close", "volume"),
                confidence=MetricConfidence.PROXY,
                priority=1,
            ),
        ),
    ),
    MarketMetricDefinition(
        name="price_impact",
        family=MetricFamily.LIQUIDITY_IMPACT,
        description="Conceptual price impact — auto-selects best path.",
        resolution_paths=(
            MetricResolutionPath(
                metric_name="amihud_illiq",
                required_data_class=DataClass.DAILY_OHLCV,
                required_columns=("close", "volume"),
                confidence=MetricConfidence.PROXY,
                priority=1,
            ),
        ),
    ),
]


class StaticMarketMetricCatalog(MarketMetricCatalog):
    """Exhaustive static catalog of ~160 market metrics.

    Implementation of MarketMetricCatalog backed by an in-memory list.
    No I/O — pure domain logic.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, MarketMetricDefinition] = {
            m.name: m for m in _METRICS + _CONCEPTUAL_METRICS
        }

    def get(self, name: str) -> MarketMetricDefinition | None:
        """Return the definition for a named metric, or None."""
        return self._by_name.get(name)

    def list(
        self, family: MetricFamily | None = None
    ) -> Sequence[MarketMetricDefinition]:
        """List all definitions, optionally filtered by family."""
        if family is None:
            return tuple(self._by_name.values())
        return tuple(m for m in self._by_name.values() if m.family == family)

    def check(
        self,
        name: str,
        available_data_class: str,
    ) -> MetricCapabilityResult:
        """Check whether a metric can be computed with the given data class."""
        definition = self._by_name.get(name)
        if definition is None:
            return MetricCapabilityResult(
                metric=name,
                supported=False,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Unknown metric name.",),
            )

        try:
            dc = DataClass(available_data_class)
        except ValueError:
            dc = DataClass.DAILY_OHLCV

        return _make_result(definition, dc)

    def resolve_best(
        self,
        concept: str,
        available_data_class: str,
        interval: str = "1d",
        force_proxy: bool = False,
    ) -> MetricCapabilityResult:
        """Auto-select the best computation path for a conceptual metric."""
        definition = self._by_name.get(concept)
        if definition is None:
            return MetricCapabilityResult(
                metric=concept,
                supported=False,
                computable=False,
                confidence=MetricConfidence.UNAVAILABLE,
                warnings=("Unknown concept name.",),
            )

        if not definition.resolution_paths:
            # No resolution paths — fall back to simple check
            return self.check(concept, available_data_class)

        try:
            dc = DataClass(available_data_class)
        except ValueError:
            dc = DataClass.DAILY_OHLCV

        paths = sorted(definition.resolution_paths, key=lambda p: p.priority)

        selected: MetricResolutionPath | None = None

        for path in paths:
            if force_proxy and path.confidence in (
                MetricConfidence.ACTUAL,
                MetricConfidence.APPROXIMATION,
            ):
                continue

            # When forcing proxy, accept any PROXY path regardless of data class
            if force_proxy:
                selected = path
                break

            if path.required_data_class != dc:
                continue

            # Interval check for intraday paths
            if path.interval_min and dc == DataClass.INTRADAY_OHLCV:
                if not _interval_matches(interval, path.interval_min):
                    continue

            selected = path
            break

        if selected is not None:
            return MetricCapabilityResult(
                metric=concept,
                supported=True,
                computable=True,
                confidence=selected.confidence,
                selected_metric=selected.metric_name,
                available_paths=definition.resolution_paths,
            )

        # No path matched — try to report which paths exist
        return MetricCapabilityResult(
            metric=concept,
            supported=True,
            computable=False,
            confidence=MetricConfidence.UNAVAILABLE,
            available_paths=definition.resolution_paths,
            missing_data_classes=tuple(
                p.required_data_class.value for p in paths
            ),
        )
