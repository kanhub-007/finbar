"""StrategyIndicatorCatalog — supported indicator metadata for strategies."""

from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)


class StrategyIndicatorCatalog(IndicatorCapabilityProvider):
    """Catalog of enrichment columns currently supported by Finbar.

    This static catalog mirrors today's enrichment layer. Future work should
    source these capabilities directly from the indicator calculator registry.
    """

    _PERIODS = {
        "sma": {10, 20, 30, 50, 200},
        "ema": {12, 26},
        "rsi": {7, 14},
    }
    _FIXED = {
        "atr": "atr",
        "adx": "adx",
        "vwap": "vwap",
        "rvol": "rvol",
        "ibs": "ibs",
        "ker": "ker",
        "kama": "kama",
        "macd": "macd",
        "macd_signal": "macd_signal",
        "macd_hist": "macd_hist",
        "bb_upper": "bb_upper",
        "bb_middle": "bb_middle",
        "bb_lower": "bb_lower",
    }

    def resolve(self, indicator_type: str, period: int | None) -> str | None:
        """Resolve an indicator type/period to a concrete enrichment column."""
        name = indicator_type.lower()
        if name in self._PERIODS:
            if period in self._PERIODS[name]:
                return f"{name}_{period}"
            return None
        return self._FIXED.get(name)

    def requires_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type requires a period."""
        return indicator_type.lower() in self._PERIODS

    def accepts_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type accepts a period argument."""
        return indicator_type.lower() in self._PERIODS

    def supports_concrete(self, name: str) -> bool:
        """Return True when a concrete enrichment column is known."""
        return name in self.supported_concrete_names()

    def supported_concrete_names(self) -> list[str]:
        """Return all concrete indicator columns currently supported."""
        names = list(self._FIXED.values())
        for indicator_type, periods in self._PERIODS.items():
            names.extend(f"{indicator_type}_{period}" for period in sorted(periods))
        return sorted(names)

    def as_dict(self) -> dict:
        """Return a JSON-serializable capabilities payload."""
        return {
            "schema_version": "2.0",
            "parameterized_indicators_enabled": False,
            "period_indicators": {
                key: {"supported_periods": sorted(values)}
                for key, values in self._PERIODS.items()
            },
            "fixed_indicators": sorted(self._FIXED),
            "supported_concrete_names": self.supported_concrete_names(),
        }
