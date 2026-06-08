"""Market Profile — Time-at-Price (TPO) based POC/VAH/VAL.

Unlike Volume Profile (which uses volume), Market Profile uses TPO
(Time Price Opportunity) counts — how many 30-minute periods "visited"
each price level. This is the original AMT tool from Steidlmayer/CBOT.

For daily bars, each bar is one session, producing degenerate profiles.
For intraday (5min/30min/1h), TPO periods are constructed from bar ranges.

All functions are pure — no state, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from finbar.core.domain.entities.market_profile_result import MarketProfileResult
from finbar.core.domain.services._profile_utils import expand_value_area

# ---------------------------------------------------------------------------
# TPO period detection
# ---------------------------------------------------------------------------

# How many bars make one 30-min TPO period for each bar interval.
_TPO_BARS_PER_PERIOD: dict[str, int] = {
    "5min": 6,
    "15min": 2,
    "30min": 1,
}


def _detect_bar_minutes(df: pd.DataFrame) -> int:
    """Detect the bar interval in minutes from the datetime index.

    Returns 0 if the index can't be parsed (e.g. string dates from daily).
    """
    if len(df) < 2:
        return 0
    try:
        # Try TimedeltaIndex first (intraday with time deltas)
        if isinstance(df.index, pd.TimedeltaIndex):
            return int(df.index[1].total_seconds() / 60)
        # DatetimeIndex
        delta = df.index[1] - df.index[0]
        return int(delta.total_seconds() / 60)
    except (TypeError, AttributeError):
        return 0


def _get_tpo_bars_per_period(df: pd.DataFrame) -> int:
    """Determine how many bars make one 30-min TPO period.

    Falls back to 2 bars for unknown intervals.
    """
    minutes = _detect_bar_minutes(df)
    for key, bars in _TPO_BARS_PER_PERIOD.items():
        if abs(minutes - int(key.replace("min", ""))) < 2:
            return bars
    if minutes >= 55:  # 1h bars: 1 bar = 2 TPO periods
        return 0  # special: split into sub-periods
    return 2  # default fallback


# ---------------------------------------------------------------------------
# TPO counting
# ---------------------------------------------------------------------------


def _count_tpos_for_bar(
    bar_high: float,
    bar_low: float,
    price_buckets: np.ndarray,
    bucket_size: float,
) -> np.ndarray:
    """Count which price buckets a single bar's range touches.

    A bucket is "touched" if the bar's high-low range overlaps it.
    Each bar contributes 1 TPO to each bucket it overlaps.

    Returns a boolean array (1 for touched, 0 for not).
    """
    half_bucket = bucket_size / 2.0
    bucket_lows = price_buckets - half_bucket
    bucket_highs = price_buckets + half_bucket

    # Overlap: bucket overlaps bar range
    touched = (bucket_highs >= bar_low) & (bucket_lows <= bar_high)

    return touched.astype(float)


def _split_1h_into_tpo_bars(
    bar: pd.Series,
) -> list[tuple[float, float]]:
    """Split a 1h bar into two 30-min TPO ranges.

    Standard Market Profile interpretation: both 30-min TPO periods
    get the full bar range, since price was available at those levels
    during the hour.
    """
    h = float(bar["high"])
    lo = float(bar["low"])
    return [(h, lo), (h, lo)]


# ---------------------------------------------------------------------------
# Session Market Profile
# ---------------------------------------------------------------------------


def compute_session_market_profile(
    session_bars: pd.DataFrame,
    num_buckets: int = 100,
) -> MarketProfileResult:
    """Build a Market Profile from a session's OHLCV bars.

    Counts TPOs (Time Price Opportunities) per price bucket, then
    extracts POC, VAH, and VAL from the TPO distribution.

    Args:
        session_bars: DataFrame with columns [open, high, low, close]
            for a single trading session.
        num_buckets: Number of price buckets (default 100).

    Returns:
        MarketProfileResult with POC, VAH, VAL, and profile data.
    """
    if session_bars.empty:
        return MarketProfileResult(
            poc=0.0, vah=0.0, val=0.0,
            total_tpos=0, value_area_tpos=0,
            bucket_size=0.0, num_buckets=num_buckets,
        )

    session_high = float(session_bars["high"].max())
    session_low = float(session_bars["low"].min())

    if session_high <= session_low:
        return MarketProfileResult(
            poc=session_high, vah=session_high, val=session_low,
            total_tpos=0, value_area_tpos=0,
            bucket_size=0.0, num_buckets=num_buckets,
        )

    # Create price buckets
    buffer = (session_high - session_low) * 0.02
    price_min = session_low - buffer
    price_max = session_high + buffer
    bucket_size = (price_max - price_min) / num_buckets
    price_buckets = np.linspace(
        price_min + bucket_size / 2,
        price_max - bucket_size / 2,
        num_buckets,
    )

    # Determine TPO period size
    tpo_bars = _get_tpo_bars_per_period(session_bars)
    use_1h_split = tpo_bars == 0

    # Count TPOs
    tpo_profile = np.zeros(num_buckets)
    total_tpos = 0

    for _, bar in session_bars.iterrows():
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])

        if use_1h_split:
            # 1h bar = 2 TPO periods
            sub_periods = _split_1h_into_tpo_bars(bar)
            for sub_high, sub_low in sub_periods:
                tpo_profile += _count_tpos_for_bar(
                    sub_high, sub_low, price_buckets, bucket_size
                )
                total_tpos += 1
        else:
            # Direct TPO count
            tpo_profile += _count_tpos_for_bar(
                bar_high, bar_low, price_buckets, bucket_size
            )
            total_tpos += 1

    if total_tpos <= 0:
        return MarketProfileResult(
            poc=float(session_bars["close"].iloc[-1]),
            vah=float(session_bars["high"].max()),
            val=float(session_bars["low"].min()),
            total_tpos=0, value_area_tpos=0,
            bucket_size=bucket_size, num_buckets=num_buckets,
        )

    # POC: price bucket with maximum TPOs
    poc_idx = int(np.argmax(tpo_profile))
    poc = float(price_buckets[poc_idx])

    # Value Area: expand outward from POC until 68% of TPOs captured
    lower_idx, upper_idx, accumulated = expand_value_area(
        tpo_profile, poc_idx, float(total_tpos)
    )

    vah = float(price_buckets[upper_idx]) + bucket_size / 2
    val = float(price_buckets[lower_idx]) - bucket_size / 2
    value_area_tpos = int(accumulated)

    # Build profile dict
    profile_dict = {
        float(price_buckets[i]): int(tpo_profile[i])
        for i in range(num_buckets)
        if tpo_profile[i] > 0
    }

    return MarketProfileResult(
        poc=poc,
        vah=vah,
        val=val,
        total_tpos=total_tpos,
        value_area_tpos=value_area_tpos,
        bucket_size=bucket_size,
        num_buckets=num_buckets,
        profile=profile_dict,
    )


# ---------------------------------------------------------------------------
# DataFrame-level computation (per-session)
# ---------------------------------------------------------------------------


def compute_all_session_market_profiles(
    df: pd.DataFrame,
    num_buckets: int = 100,
) -> pd.DataFrame:
    """Compute Market Profile POC/VAH/VAL for each session in a DataFrame.

    Groups bars by calendar date, computes a Market Profile per session,
    and broadcasts POC/VAH/VAL to all bars in that session.

    Args:
        df: DataFrame with columns [open, high, low, close]
            and a datetime index.
        num_buckets: Number of price buckets per profile.

    Returns:
        DataFrame with added columns: mp_poc, mp_vah, mp_val.
    """
    result = df.copy()
    result["mp_poc"] = np.nan
    result["mp_vah"] = np.nan
    result["mp_val"] = np.nan

    date_series = pd.Series(
        pd.to_datetime(result.index).strftime("%Y-%m-%d"), index=result.index
    )

    for date, idx in date_series.groupby(date_series).groups.items():
        session = df.loc[idx]
        profile = compute_session_market_profile(session, num_buckets=num_buckets)

        result.loc[idx, "mp_poc"] = profile.poc
        result.loc[idx, "mp_vah"] = profile.vah
        result.loc[idx, "mp_val"] = profile.val

    return result
