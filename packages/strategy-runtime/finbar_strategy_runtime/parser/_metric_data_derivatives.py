"""Derivatives metric definitions — metric definitions shard (data only).

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
        name="funding_rate",
        family=MetricFamily.DERIVATIVES,
        description="Perpetual funding rate from exchange/CoinGlass.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="open_interest",
        family=MetricFamily.DERIVATIVES,
        description="Aggregate open interest from exchange/CoinGlass.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="open_interest_delta_1h",
        family=MetricFamily.DERIVATIVES,
        description="1-hour change in open interest.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="open_interest_delta_24h",
        family=MetricFamily.DERIVATIVES,
        description="24-hour change in open interest.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="cumulative_volume_delta",
        family=MetricFamily.DERIVATIVES,
        description="CVD: cumulative delta between buying and selling volume.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="long_short_ratio",
        family=MetricFamily.DERIVATIVES,
        description="Long/short ratio from exchange/CoinGlass.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="liquidations_long_1h",
        family=MetricFamily.DERIVATIVES,
        description="Long liquidations in the last hour.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="liquidations_short_1h",
        family=MetricFamily.DERIVATIVES,
        description="Short liquidations in the last hour.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="liquidations_long_24h",
        family=MetricFamily.DERIVATIVES,
        description="Long liquidations in the last 24 hours.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="liquidations_short_24h",
        family=MetricFamily.DERIVATIVES,
        description="Short liquidations in the last 24 hours.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
MarketMetricDefinition(
        name="funding_rate_annualised",
        family=MetricFamily.DERIVATIVES,
        description="Annualised funding rate.",
        required_data_classes=(DataClass.DAILY_OHLCV, DataClass.INTRADAY_OHLCV),
        required_providers=("coinglass",),
        min_lookback=1,
        confidence=MetricConfidence.ACTUAL,
    ),
]
