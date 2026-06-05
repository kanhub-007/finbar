"""StrategyIndicatorCatalog — supported indicator metadata for strategies."""

from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)


class StrategyIndicatorCatalog(IndicatorCapabilityProvider):
    """Catalog of enrichment columns currently supported by Finbar.

    This static catalog mirrors today's enrichment layer. Future work should
    source these capabilities directly from the indicator calculator registry.
    """

    _PERIOD_RANGES = {
        "sma": (2, 500),
        "ema": (2, 500),
        "rsi": (2, 100),
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
        if name in self._PERIOD_RANGES:
            min_p, max_p = self._PERIOD_RANGES[name]
            if isinstance(period, int) and min_p <= period <= max_p:
                return f"{name}_{period}"
            return None
        return self._FIXED.get(name)

    def requires_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type requires a period."""
        return indicator_type.lower() in self._PERIOD_RANGES

    def accepts_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type accepts a period argument."""
        return indicator_type.lower() in self._PERIOD_RANGES

    def supports_concrete(self, name: str) -> bool:
        """Return True when a concrete enrichment column is known."""
        if name in self._FIXED or name in self._FIXED.values():
            return True
        for prefix in self._PERIOD_RANGES:
            if name.startswith(f"{prefix}_"):
                rest = name[len(prefix) + 1 :]
                if rest.isdigit():
                    return True
        return False

    def supported_concrete_names(self) -> list[str]:
        """Return all concrete indicator columns currently supported."""
        names = list(self._FIXED.values())
        for indicator_type, (min_p, max_p) in self._PERIOD_RANGES.items():
            names.extend(
                f"{indicator_type}_{period}"
                for period in range(min_p, min(min_p + 5, max_p + 1))
            )
        return sorted(names)

    def as_dict(self) -> dict:
        """Return a JSON-serializable capabilities payload."""
        return {
            "schema_version": "2.0",
            "parameterized_indicators_enabled": True,
            "period_ranges": {
                key: {"min": min_p, "max": max_p}
                for key, (min_p, max_p) in self._PERIOD_RANGES.items()
            },
            "fixed_indicators": sorted(self._FIXED),
            "supported_concrete_names": "any period within ranges for sma/ema/rsi",
        }
