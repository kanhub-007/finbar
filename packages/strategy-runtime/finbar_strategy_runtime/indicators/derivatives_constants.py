"""Constants for derivatives metrics shared across the runtime package.

This module defines the canonical list of derivatives field names.
Both the indicator calculator (pass-through handlers) and any future
merge logic in the package reference this list.
"""

# All nullable float field names for derivatives metrics that can be
# merged onto OHLCV frames and used as indicator columns.
DERIVATIVES_FIELDS: tuple[str, ...] = (
    "open_interest",
    "open_interest_delta_1h",
    "open_interest_delta_24h",
    "cumulative_volume_delta",
    "funding_rate",
    "funding_rate_annualised",
    "long_short_ratio",
    "liquidations_long_1h",
    "liquidations_short_1h",
    "liquidations_long_24h",
    "liquidations_short_24h",
)
