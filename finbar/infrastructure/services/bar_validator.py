"""OHLCV bar validation — sanity checks before caching.
(_validate_bar method). Extracted as a standalone function.
"""

import logging

logger = logging.getLogger(__name__)


def validate_bar(
    symbol: str,
    timestamp: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int | None,
) -> bool:
    """Validate OHLCV values for logical consistency.

    Drops invalid bars with a warning log. Rules:
    - high must be >= low
    - close and open must be positive
    - volume must be non-negative (if present)

    Args:
        symbol: Ticker symbol (for logging).
        timestamp: Bar timestamp (for logging).
        open_price: Opening price.
        high: Highest price.
        low: Lowest price.
        close: Closing price.
        volume: Trading volume (may be None).

    Returns:
        True if the bar is valid, False if it should be dropped.
    """
    if high < low:
        logger.warning(
            "Invalid bar dropped for %s at %s: high (%s) < low (%s)",
            symbol,
            timestamp,
            high,
            low,
        )
        return False
    if close <= 0 or open_price <= 0:
        logger.warning(
            "Invalid bar dropped for %s at %s: non-positive price "
            "(open=%s, close=%s)",
            symbol,
            timestamp,
            open_price,
            close,
        )
        return False
    if volume is not None and volume < 0:
        logger.warning(
            "Invalid bar dropped for %s at %s: negative volume (%s)",
            symbol,
            timestamp,
            volume,
        )
        return False
    return True
