"""Spread metric definitions — metric definitions shard (data only).

Split from ``_metric_data.py`` by family group to keep each file under the
500-line review threshold. Aggregated by ``_metric_data.py``.
"""

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily

METRICS: list[MarketMetricDefinition] = [
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
        name="effective_tick_spread",
        family=MetricFamily.SPREAD,
        description="Tick-based spread estimator using close-to-close price clustering.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=60,
        confidence=MetricConfidence.PROXY,
        paper_reference="Holden (2009), 'New Low-Frequency Spread Measures'",
        condition_note="Requires at least 60 bars for the lookback window.",
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
        name="lot_zero_return_spread",
        family=MetricFamily.SPREAD,
        description="LOT spread from zero-return proportion.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_columns=("close",),
        min_lookback=60,
        confidence=MetricConfidence.PROXY,
        paper_reference="Lesmond, Ogden & Trzcinka (1999), 'A New Estimate of Transaction Costs'",
        condition_note="Requires at least 60 bars for the lookback window.",
    ),
]
