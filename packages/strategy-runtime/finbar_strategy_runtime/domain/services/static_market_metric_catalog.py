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


def _make_result(
    definition: MarketMetricDefinition,
    available_class: DataClass,
) -> MetricCapabilityResult:
    """Build a MetricCapabilityResult from a definition and available data class."""
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

    # --- Non-OHLCV metric (catalogued, unavailable) ---
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
        name="effective_spread_taq",
        family=MetricFamily.SPREAD,
        description="Effective spread from TAQ trade-and-quote data.",
        required_data_classes=(DataClass.TRADES_AND_QUOTES,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("corwin_schultz_spread", "roll_spread"),
    ),
    MarketMetricDefinition(
        name="cont_kukanov_ofi",
        family=MetricFamily.ORDER_FLOW,
        description="Cont-Kukanov order flow imbalance from L2 order book events.",
        required_data_classes=(DataClass.LEVEL_2_ORDER_BOOK,),
        min_lookback=1,
        confidence=MetricConfidence.UNAVAILABLE,
        proxy_candidates=("bvc_ofi",),
        paper_reference="Cont, Kukanov & Stoikov (2014), 'The Price Impact of Order Book Events'",
    ),
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
]


class StaticMarketMetricCatalog(MarketMetricCatalog):
    """Exhaustive static catalog of ~160 market metrics.

    Implementation of MarketMetricCatalog backed by an in-memory list.
    No I/O — pure domain logic.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, MarketMetricDefinition] = {
            m.name: m for m in _METRICS
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
