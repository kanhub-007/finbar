"""StrategyIndicatorCatalog — supported indicator metadata for strategies."""

from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)


class StrategyIndicatorCatalog(IndicatorCapabilityProvider):
    """Catalog of indicator columns currently supported by Finbar."""

    _PERIOD_RANGES = {
        "sma": (2, 500),
        "ema": (2, 500),
        "rsi": (2, 100),
    }
    _OPTIONAL_PERIOD_RANGES = {
        "atr": (2, 200),
        "adx": (2, 100),
        "bb_upper": (2, 200),
        "bb_middle": (2, 200),
        "bb_lower": (2, 200),
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
        # --- Proxy quantitative indicators ---
        "proxy_atr": "proxy_atr",
        "proxy_vwap": "proxy_vwap",
        "proxy_ibs": "proxy_ibs",
        "proxy_ib_high": "proxy_ib_high",
        "proxy_ib_low": "proxy_ib_low",
        "proxy_expected_move": "proxy_expected_move",
        "proxy_parkinson": "proxy_parkinson",
        "proxy_garman_klass": "proxy_garman_klass",
        "proxy_rogers_satchell": "proxy_rogers_satchell",
        # --- Intraday session metrics (real, not proxy) ---
        "ib_high": "ib_high",
        "ib_low": "ib_low",
        "ib_range": "ib_range",
        # --- Volume buffer levels ---
        "vol_buffer_high": "vol_buffer_high",
        "vol_buffer_low": "vol_buffer_low",
        # --- Support / resistance ---
        "swing_high_20": "swing_high_20",
        "swing_low_20": "swing_low_20",
        "breakout_level": "breakout_level",
        "breakout_signal": "breakout_signal",
        "is_power_zone": "is_power_zone",
        "breakout_quality": "breakout_quality",
        # --- Trend classification ---
        "price_vs_sma20": "price_vs_sma20",
        "trend_direction": "trend_direction",
        "trend_strength": "trend_strength",
        "trend_status": "trend_status",
        # --- Initial Balance ---
        "ib_midpoint": "ib_midpoint",
    }

    def resolve(self, indicator_type: str, period: int | None) -> str | None:
        """Resolve an indicator type/period to a concrete indicator column."""
        name = indicator_type.lower()
        if name in self._PERIOD_RANGES:
            min_p, max_p = self._PERIOD_RANGES[name]
            if isinstance(period, int) and min_p <= period <= max_p:
                return f"{name}_{period}"
            return None
        if name in self._OPTIONAL_PERIOD_RANGES:
            min_p, max_p = self._OPTIONAL_PERIOD_RANGES[name]
            if period is None:
                return self._FIXED.get(name)
            if isinstance(period, int) and min_p <= period <= max_p:
                return f"{name}_{period}"
            return None
        return self._FIXED.get(name)

    def requires_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type requires a period."""
        return indicator_type.lower() in self._PERIOD_RANGES

    def accepts_period(self, indicator_type: str) -> bool:
        """Return True when the indicator type accepts a period argument."""
        name = indicator_type.lower()
        return name in self._PERIOD_RANGES or name in self._OPTIONAL_PERIOD_RANGES

    def supports_concrete(self, name: str) -> bool:
        """Return True when a concrete indicator column is known."""
        if name in self._FIXED or name in self._FIXED.values():
            return True
        for suffix in ("_1d", "_1h", "_30min", "_5min", "_1w"):
            if name.endswith(suffix):
                return self.supports_concrete(name[: -len(suffix)])
        for prefix in self._PERIOD_RANGES:
            if name.startswith(f"{prefix}_"):
                rest = name[len(prefix) + 1 :]
                if rest.isdigit():
                    return True
        for prefix in self._OPTIONAL_PERIOD_RANGES:
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
        for indicator_type, (min_p, max_p) in self._OPTIONAL_PERIOD_RANGES.items():
            names.extend(
                f"{indicator_type}_{period}"
                for period in range(min_p, min(min_p + 3, max_p + 1))
            )
        return sorted(names)

    def as_dict(self) -> dict:
        """Return a JSON-serializable capabilities payload."""
        period_ranges = {
            key: {"min": min_p, "max": max_p, "required": True}
            for key, (min_p, max_p) in self._PERIOD_RANGES.items()
        }
        optional_ranges = {
            key: {"min": min_p, "max": max_p, "required": False}
            for key, (min_p, max_p) in self._OPTIONAL_PERIOD_RANGES.items()
        }
        period_ranges.update(optional_ranges)
        return {
            "schema_version": "2.0",
            "parameterized_indicators_enabled": True,
            "period_ranges": period_ranges,
            "fixed_indicators": sorted(self._FIXED),
            "supported_concrete_names": (
                "any period within ranges for sma/ema/rsi/atr/adx"
            ),
        }
