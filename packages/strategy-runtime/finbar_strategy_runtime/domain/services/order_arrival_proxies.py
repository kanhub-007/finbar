"""Order arrival proxy calculators from OHLCV data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def volume_to_trade_count_proxy(
    volume: pd.Series,
    avg_trade_size: float = 500.0,
) -> pd.Series:
    """Estimate trade count from volume and average trade size.

    Args:
        volume: Series of volume values.
        avg_trade_size: Estimated average trade size.

    Returns:
        Series of estimated trade counts.
    """
    if avg_trade_size <= 0:
        return pd.Series(np.nan, index=volume.index)
    return volume.astype(float) / avg_trade_size



