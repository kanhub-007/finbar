"""Order flow proxy calculators from OHLCV data.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Signed sqrt(volume) OFI
# ---------------------------------------------------------------------------


def signed_sqrt_volume_ofi(df: pd.DataFrame) -> pd.Series:
    """Signed square-root of volume order flow imbalance.

    Chordia & Subrahmanyam (2004): OFI ≈ sign(Δclose) * sqrt(volume).

    Args:
        df: DataFrame with 'close' and 'volume' columns.

    Returns:
        Series of OFI values (same index as input).
    """
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    delta = close.diff()
    sqrt_vol = np.sqrt(volume)

    result = pd.Series(0.0, index=df.index)
    result[1:] = np.sign(delta[1:]) * sqrt_vol[1:]
    result.iloc[0] = 0.0

    return result


# ---------------------------------------------------------------------------
# Cumulative signed sqrt(volume) OFI
# ---------------------------------------------------------------------------


def cumulative_signed_volume_ofi(
    df: pd.DataFrame,
) -> pd.Series:
    """Cumulative sum of signed sqrt(volume) OFI.

    Args:
        df: DataFrame with 'close' and 'volume' columns.

    Returns:
        Series of cumulative OFI values.
    """
    ofi = signed_sqrt_volume_ofi(df)
    return ofi.cumsum()


# ---------------------------------------------------------------------------
# BVC (Bulk Volume Classification) — ELO (2012)
# ---------------------------------------------------------------------------


def _bvc_components(
    df: pd.DataFrame,
    volatility_col: str | None = None,
    lookback: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """Compute BVC buy and sell volume estimates.

    Easley, Lopez de Prado & O'Hara (2012): 'The Volume Clock: Insights
    into the High-Frequency Paradigm.'  Journal of Portfolio Management.

    BVC uses a normal CDF of standardized price change to estimate the
    proportion of volume that is buyer-initiated.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        volatility_col: Name of pre-computed volatility column, or None
            to compute close-to-close vol internally.
        lookback: Window for volatility estimation if volatility_col is None.

    Returns:
        Tuple of (buy_volume, sell_volume) Series.
    """
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    delta = close.diff()

    if volatility_col and volatility_col in df.columns:
        vol_est = df[volatility_col].astype(float)
    else:
        ret = close.pct_change()
        vol_est = ret.rolling(lookback).std() * close

    # Standardized price change
    z = delta / vol_est.replace(0, np.nan)

    # Normal CDF via approximation
    from math import erf

    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + erf(x / np.sqrt(2.0)))

    # Buy proportion = Φ(z / σ)
    buy_prop = z.apply(lambda x: _norm_cdf(x) if pd.notna(x) else np.nan)

    buy_vol = buy_prop * volume
    sell_vol = (1.0 - buy_prop) * volume

    return buy_vol, sell_vol


def bvc_buy_volume(
    df: pd.DataFrame,
    volatility_col: str | None = None,
    lookback: int = 20,
) -> pd.Series:
    """BVC-estimated buyer-initiated volume.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        volatility_col: Optional pre-computed volatility column name.
        lookback: Volatility estimation window.

    Returns:
        Series of buy volume estimates.
    """
    buy, _ = _bvc_components(df, volatility_col, lookback)
    return buy


def bvc_sell_volume(
    df: pd.DataFrame,
    volatility_col: str | None = None,
    lookback: int = 20,
) -> pd.Series:
    """BVC-estimated seller-initiated volume.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        volatility_col: Optional pre-computed volatility column name.
        lookback: Volatility estimation window.

    Returns:
        Series of sell volume estimates.
    """
    _, sell = _bvc_components(df, volatility_col, lookback)
    return sell


def bvc_ofi(
    df: pd.DataFrame,
    volatility_col: str | None = None,
    lookback: int = 20,
) -> pd.Series:
    """BVC order flow imbalance: buy_volume - sell_volume.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        volatility_col: Optional pre-computed volatility column name.
        lookback: Volatility estimation window.

    Returns:
        Series of OFI values.
    """
    buy, sell = _bvc_components(df, volatility_col, lookback)
    return buy - sell
