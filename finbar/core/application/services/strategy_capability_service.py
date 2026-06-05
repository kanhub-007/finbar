"""StrategyCapabilityService — compose SDK capability metadata."""

from finbar.core.application.services.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)

_FEATURE_TYPES = [
    "rolling_max",
    "rolling_min",
    "rolling_mean",
    "rolling_std",
    "shift",
    "body_pct",
    "range_pct",
    "typical_price",
    "ohlc4",
]
_OPERATORS = [
    "<",
    ">",
    "<=",
    ">=",
    "==",
    "!=",
    "crosses_above",
    "crosses_below",
    "between",
    "not_between",
    "is_true",
    "is_false",
    "exists",
    "missing",
]


class StrategyCapabilityService:
    """Return machine-readable capabilities for strategy authoring."""

    def __init__(self, catalog: IndicatorCapabilityProvider | None = None):
        """Create the service with injectable indicator capabilities."""
        self._catalog = catalog or StrategyIndicatorCatalog()

    def get_capabilities(self) -> dict:
        """Return the current strategy SDK capabilities."""
        return {
            "schema_version": "2.0",
            "orchestration": [
                "validate_strategy_json",
                "fetch/query prices",
                "apply_indicators separately",
                "apply_strategy_features separately",
                "backtest_strategy_json with enriched bars",
            ],
            "backtest_calculates_indicators": False,
            "backtest_calculates_features": False,
            "fields": ["timestamp", "open", "high", "low", "close", "volume"],
            "features": {"supported_types": _FEATURE_TYPES},
            "multi_timeframe": {
                "supported": True,
                "max_informative_timeframes": 3,
                "primary_alias": "primary",
                "column_naming": "{indicator}_{informative_interval}",
                "example_column": "sma_50_1d",
                "workflow": [
                    "fetch primary bars",
                    "fetch informative bars",
                    "apply primary indicators to primary bars",
                    "apply informative indicators to informative bars",
                    "call backtest_strategy_json with informative_bars_json",
                ],
            },
            "risk": {
                "stop_loss_types": ["none", "atr", "fixed_pct"],
                "take_profit_types": ["none", "atr", "fixed_pct", "risk_reward"],
            },
            "operators": _OPERATORS,
            "indicators": self._catalog.as_dict(),
        }
