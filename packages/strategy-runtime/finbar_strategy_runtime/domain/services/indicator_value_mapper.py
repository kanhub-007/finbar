"""IndicatorValueMapper — convert categorical indicator values to numeric.

Domain service — maps well-known string enum values from technical
indicators (trend_strength, trend_direction, breakout_signal) to
numeric floats usable in timeframe merging and condition evaluation.
"""

from typing import Any

# ── Known categorical indicator value mappings ──────────────────────────
_CATEGORICAL_MAP: dict[str, float] = {
    # trend_strength
    "STRONG": 3.0,
    "MODERATE": 2.0,
    "WEAK": 1.0,
    # trend_direction
    "UP": 1.0,
    "DOWN": -1.0,
    "NEUTRAL": 0.0,
    "RANGING": 0.0,
    "FLAT": 0.0,
    # breakout_signal
    "BULLISH": 1.0,
    "BEARISH": -1.0,
    "NONE": 0.0,
}


def to_numeric(value: Any) -> float | None:
    """Convert a bar value to float, handling categorical indicator strings.

    Numeric values are passed through directly. Strings are matched
    against the known categorical map. Unknown strings return None
    rather than raising — the caller decides how to handle them.

    Args:
        value: Raw bar value (int, float, str, etc.)

    Returns:
        Float representation, or None if the value is unmappable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        mapped = _CATEGORICAL_MAP.get(value.upper())
        if mapped is not None:
            return mapped
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
