"""Proxy Volume Profile — approximate POC/VAH/VAL from OHLCV bars.

Since finbar has OHLCV data (not tick-level volume-at-price), we
approximate the volume distribution within each bar using Parkinson
volatility as the spread parameter. Volume is modeled as normally
distributed around the bar's typical price, truncated to the bar's
high-low range.

Per-session, volume from all bars is aggregated into price buckets,
and the 68% Value Area with Point of Control is extracted.

All functions are pure — no state, no I/O.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from finbar_strategy_runtime.domain.entities.volume_profile_result import (
    VolumeProfileResult,
)
from finbar_strategy_runtime.domain.services._profile_utils import expand_value_area
from finbar_strategy_runtime.domain.services.metric_input_guard import (
    require_metric_columns,
)

# ---------------------------------------------------------------------------
# Per-bar volume distribution
# ---------------------------------------------------------------------------


def _parkinson_sigma(high: float, low: float) -> float:
    """Parkinson (1980) volatility for a single bar: ln(H/L) / (2·√ln2)."""
    if low <= 0 or high <= low:
        return 0.0
    return math.log(high / low) / (2.0 * math.sqrt(math.log(2)))


def _session_bucket_grid(
    session_high: float,
    session_low: float,
    num_buckets: int,
) -> tuple[np.ndarray, float]:
    """Build the price-bucket grid for one session (with a 2% buffer).

    Returns ``(price_buckets, bucket_size)``.
    """
    buffer = (session_high - session_low) * 0.02
    price_min = session_low - buffer
    price_max = session_high + buffer
    bucket_size = (price_max - price_min) / num_buckets
    price_buckets = np.linspace(
        price_min + bucket_size / 2,
        price_max - bucket_size / 2,
        num_buckets,
    )
    return price_buckets, bucket_size


def _aggregate_session_volume(
    session_bars: pd.DataFrame,
    price_buckets: np.ndarray,
    bucket_size: float,
) -> tuple[np.ndarray, float]:
    """Distribute each bar's volume across the price buckets.

    Columns are extracted to numpy arrays once and indexed by position to
    avoid the per-bar pd.Series allocation overhead of iterrows().
    Returns ``(volume_profile, total_volume)``.
    """
    highs = session_bars["high"].to_numpy()
    lows = session_bars["low"].to_numpy()
    closes = session_bars["close"].to_numpy()
    volumes = session_bars["volume"].to_numpy()

    volume_profile = np.zeros(len(price_buckets))
    total_volume = 0.0
    for j in range(len(highs)):
        raw_volume = volumes[j]
        bar_volume = float(raw_volume) if raw_volume > 0 else 0.0
        if bar_volume <= 0:
            continue
        total_volume += bar_volume
        volume_profile += _distribute_bar_volume(
            float(highs[j]),
            float(lows[j]),
            float(closes[j]),
            bar_volume,
            price_buckets,
            bucket_size,
        )
    return volume_profile, total_volume


def _build_volume_profile_result(
    volume_profile: np.ndarray,
    price_buckets: np.ndarray,
    bucket_size: float,
    total_volume: float,
    num_buckets: int,
) -> VolumeProfileResult:
    """Extract POC/VAH/VAL from an aggregated profile and build the result."""
    poc_idx = int(np.argmax(volume_profile))
    poc = float(price_buckets[poc_idx])
    lower_idx, upper_idx, accumulated = expand_value_area(
        volume_profile, poc_idx, total_volume
    )
    vah = float(price_buckets[upper_idx]) + bucket_size / 2
    val = float(price_buckets[lower_idx]) - bucket_size / 2
    profile_dict = {
        float(price_buckets[i]): float(volume_profile[i])
        for i in range(num_buckets)
        if volume_profile[i] > 0
    }
    return VolumeProfileResult(
        poc=poc,
        vah=vah,
        val=val,
        total_volume=total_volume,
        value_area_volume=float(accumulated),
        bucket_size=bucket_size,
        num_buckets=num_buckets,
        profile=profile_dict,
    )


def _distribute_bar_volume(
    bar_high: float,
    bar_low: float,
    bar_close: float,
    bar_volume: float,
    price_buckets: np.ndarray,
    bucket_size: float,
) -> np.ndarray:
    """Distribute one bar's volume across price buckets.

    Uses a normal distribution centered at typical price with
    Parkinson-derived sigma, truncated to [bar_low, bar_high].

    Args:
        bar_high: Bar high price.
        bar_low: Bar low price.
        bar_close: Bar close price.
        bar_volume: Total volume for this bar.
        price_buckets: Array of bucket center prices.
        bucket_size: Width of each price bucket.

    Returns:
        Array of volume per bucket for this bar.
    """
    tp = (bar_high + bar_low + bar_close) / 3.0
    sigma = _parkinson_sigma(bar_high, bar_low)

    if sigma <= 0 or bar_volume <= 0:
        # Degenerate bar — assign all volume to nearest bucket
        result = np.zeros(len(price_buckets))
        if len(price_buckets) > 0:
            nearest = np.argmin(np.abs(price_buckets - tp))
            result[nearest] = bar_volume
        return result

    # Normal PDF evaluated at each bucket center
    z = (price_buckets - tp) / sigma
    pdf = np.exp(-0.5 * z**2) / (sigma * math.sqrt(2 * math.pi))

    # Truncate to bar's high-low range with soft edges
    half_bucket = bucket_size / 2.0
    below_low = price_buckets + half_bucket < bar_low
    above_high = price_buckets - half_bucket > bar_high

    # Attenuate buckets outside bar's high-low range
    pdf[below_low | above_high] *= 0.1

    total_pdf = pdf.sum()
    if total_pdf <= 0:
        return np.zeros(len(price_buckets))

    return (pdf / total_pdf) * bar_volume


# ---------------------------------------------------------------------------
# Session Volume Profile
# ---------------------------------------------------------------------------


def compute_session_volume_profile(
    session_bars: pd.DataFrame,
    num_buckets: int = 100,
) -> VolumeProfileResult:
    """Build an approximate Volume Profile from a session's OHLCV bars.

    Aggregates volume from all bars into price buckets, using
    Parkinson-weighted normal distribution within each bar, then
    extracts POC, VAH, and VAL from the resulting profile.

    Args:
        session_bars: DataFrame with columns [high, low, close, volume]
            for a single trading session.
        num_buckets: Number of price buckets (default 100).

    Returns:
        VolumeProfileResult with POC, VAH, VAL, and profile data.
    """
    if session_bars.empty:
        return VolumeProfileResult(
            poc=0.0,
            vah=0.0,
            val=0.0,
            total_volume=0.0,
            value_area_volume=0.0,
            bucket_size=0.0,
            num_buckets=num_buckets,
        )

    session_high = float(session_bars["high"].max())
    session_low = float(session_bars["low"].min())

    if session_high <= session_low:
        return VolumeProfileResult(
            poc=session_high,
            vah=session_high,
            val=session_low,
            total_volume=0.0,
            value_area_volume=0.0,
            bucket_size=0.0,
            num_buckets=num_buckets,
        )

    # Create price buckets spanning the session range with a small buffer
    price_buckets, bucket_size = _session_bucket_grid(
        session_high, session_low, num_buckets
    )
    volume_profile, total_volume = _aggregate_session_volume(
        session_bars, price_buckets, bucket_size
    )

    if total_volume <= 0:
        return VolumeProfileResult(
            poc=float(session_bars["close"].iloc[-1]),
            vah=float(session_bars["high"].max()),
            val=float(session_bars["low"].min()),
            total_volume=0.0,
            value_area_volume=0.0,
            bucket_size=bucket_size,
            num_buckets=num_buckets,
        )

    return _build_volume_profile_result(
        volume_profile, price_buckets, bucket_size, total_volume, num_buckets
    )


# ---------------------------------------------------------------------------
# DataFrame-level computation (per-session)
# ---------------------------------------------------------------------------


def compute_all_session_volume_profiles(
    df: pd.DataFrame,
    num_buckets: int = 100,
) -> pd.DataFrame:
    """Compute Volume Profile POC/VAH/VAL for each session in a DataFrame.

    Groups bars by calendar date, computes a Volume Profile per session,
    and broadcasts POC/VAH/VAL to all bars in that session.

    Args:
        df: DataFrame with columns [high, low, close, volume]
            and a datetime index.
        num_buckets: Number of price buckets per profile.

    Returns:
        DataFrame with added columns: vp_poc, vp_vah, vp_val.
    """
    result = df.copy()
    result["vp_poc"] = np.nan
    result["vp_vah"] = np.nan
    result["vp_val"] = np.nan

    date_series = pd.Series(result.index.date, index=result.index)

    # Compute per-session profiles and accumulate (date -> values),
    # then broadcast via a single map(). This avoids the per-session
    # ``result.loc[idx, col] =`` alignment overhead.
    poc_map: dict = {}
    vah_map: dict = {}
    val_map: dict = {}

    for date, idx in date_series.groupby(date_series).groups.items():
        session = df.loc[idx]
        profile = compute_session_volume_profile(session, num_buckets=num_buckets)
        poc_map[date] = profile.poc
        vah_map[date] = profile.vah
        val_map[date] = profile.val

    result["vp_poc"] = date_series.map(poc_map)
    result["vp_vah"] = date_series.map(vah_map)
    result["vp_val"] = date_series.map(val_map)

    return result


# ---------------------------------------------------------------------------
# Expanding current-session Volume Profile (live-parity)
# ---------------------------------------------------------------------------


def compute_expanding_session_volume_profiles(
    df: pd.DataFrame,
    num_buckets: int = 100,
) -> pd.DataFrame:
    """Compute expanding current-session Volume Profile (live-parity).

    For each bar ``t``, ``vp_poc`` / ``vp_vah`` / ``vp_val`` are computed
    from the current session's bars from session open through ``t`` only.
    No later bar in the same session influences an earlier row. This is
    the causal definition that matches Finbot WebSocket/prefix behaviour
    and is the required oracle for live-parity backtests.

    Contrast with :func:`compute_all_session_volume_profiles`, which
    broadcasts one completed-session profile to every row in the session
    (batch/research behaviour, explicitly NOT live-parity safe).

    Args:
        df: DataFrame with columns ``[high, low, close, volume]`` and a
            timezone-aware DatetimeIndex sorted ascending.
        num_buckets: Number of price buckets per profile.

    Returns:
        DataFrame with added columns: ``vp_poc``, ``vp_vah``, ``vp_val``.
    """
    result = df.copy()
    n = len(result)
    poc_vals = np.full(n, np.nan)
    vah_vals = np.full(n, np.nan)
    val_vals = np.full(n, np.nan)

    result["vp_poc"] = poc_vals
    result["vp_vah"] = vah_vals
    result["vp_val"] = val_vals
    if n == 0:
        return result

    date_array = np.array([idx.date() for idx in result.index])

    # Sessions are contiguous because the index is sorted ascending: walk
    # runs of equal calendar date and, within each session, recompute the
    # profile over the expanding prefix ending at each bar.
    i = 0
    while i < n:
        session_start = i
        current_date = date_array[i]
        while i < n and date_array[i] == current_date:
            i += 1
        session = result.iloc[session_start:i]
        for k in range(len(session)):
            prefix = session.iloc[: k + 1]
            profile = compute_session_volume_profile(
                prefix, num_buckets=num_buckets
            )
            pos = session_start + k
            poc_vals[pos] = profile.poc
            vah_vals[pos] = profile.vah
            val_vals[pos] = profile.val

    result["vp_poc"] = poc_vals
    result["vp_vah"] = vah_vals
    result["vp_val"] = val_vals
    return result


# ---------------------------------------------------------------------------
# Rolling / Composite Value Areas
# ---------------------------------------------------------------------------


def compute_rolling_vp(
    df: pd.DataFrame,
    window: int = 5,
) -> pd.DataFrame:
    """Compute rolling N-session median of Volume Profile POC/VAH/VAL.

    Groups by session, extracts one value per session, computes
    rolling median over ``window`` sessions, and broadcasts to all
    bars in each session.

    Requires: vp_poc, vp_vah, vp_val columns already on df.

    Args:
        df: DataFrame with vp_poc, vp_vah, vp_val columns.
        window: Number of sessions in rolling window (default 5).

    Returns:
        DataFrame with added columns: vp_poc_{window}d, vp_vah_{window}d,
        vp_val_{window}d.
    """
    result = df.copy()

    poc_col = f"vp_poc_{window}d"
    vah_col = f"vp_vah_{window}d"
    val_col = f"vp_val_{window}d"

    result[poc_col] = np.nan
    result[vah_col] = np.nan
    result[val_col] = np.nan

    require_metric_columns(
        result,
        "compute_rolling_vp",
        ("vp_poc", "vp_vah", "vp_val"),
    )

    date_series = pd.Series(
        result.index.date,
        index=result.index,
    )

    # Extract one value per session (all bars in a session share the same VP)
    session_poc: dict[str, float] = {}
    session_vah: dict[str, float] = {}
    session_val: dict[str, float] = {}

    for date, idx in date_series.groupby(date_series).groups.items():
        session_poc[date] = float(df["vp_poc"].loc[idx].iloc[-1])
        session_vah[date] = float(df["vp_vah"].loc[idx].iloc[-1])
        session_val[date] = float(df["vp_val"].loc[idx].iloc[-1])

    ordered_dates = sorted(session_poc.keys())

    if len(ordered_dates) < window:
        return result

    # Rolling median over sessions. Build arrays once and use np.median
    # on slices, then broadcast via map() to avoid per-session .loc writes.
    poc_vals = np.array([session_poc[d] for d in ordered_dates], dtype=float)
    vah_vals = np.array([session_vah[d] for d in ordered_dates], dtype=float)
    val_vals = np.array([session_val[d] for d in ordered_dates], dtype=float)

    rolling_poc_map: dict = {}
    rolling_vah_map: dict = {}
    rolling_val_map: dict = {}

    for i in range(window - 1, len(ordered_dates)):
        s = slice(i - window + 1, i + 1)
        rolling_poc_map[ordered_dates[i]] = float(np.median(poc_vals[s]))
        rolling_vah_map[ordered_dates[i]] = float(np.median(vah_vals[s]))
        rolling_val_map[ordered_dates[i]] = float(np.median(val_vals[s]))

    result[poc_col] = date_series.map(rolling_poc_map)
    result[vah_col] = date_series.map(rolling_vah_map)
    result[val_col] = date_series.map(rolling_val_map)

    return result


# ---------------------------------------------------------------------------
# Rolling-window Volume Profile — bar-based windows (24/7 crypto markets)
# ---------------------------------------------------------------------------


def compute_rolling_window_vp(
    df: pd.DataFrame,
    window_bars: int = 48,
    num_buckets: int = 100,
) -> pd.DataFrame:
    """Compute Volume Profile over a trailing bar window.

    Unlike session-based VP (which groups by calendar date), this uses
    a rolling N-bar window. Each bar gets POC/VAH/VAL computed from the
    trailing ``window_bars`` bars. Works for any market — crypto (24/7),
    equities (with after-hours), forex.

    Implementation: a single fixed bucket grid spanning the whole frame's
    price range is used for every window. The running volume profile is
    updated incrementally — each bar adds its distributed volume and the
    bar leaving the window is subtracted — so each bar costs O(buckets)
    rather than O(window*buckets). This is ~window/2x faster than rebuilding
    the full profile from scratch per bar (e.g. ~24x for window=48).

    Args:
        df: DataFrame with columns [high, low, close, volume]
            and a datetime index.
        window_bars: Number of bars in the trailing window (default 48 =
            24 hours at 30min).
        num_buckets: Number of price buckets per profile.

    Returns:
        DataFrame with added columns: rvp_poc_{window_bars},
        rvp_vah_{window_bars}, rvp_val_{window_bars}.
    """
    result = df.copy()

    poc_col = f"rvp_poc_{window_bars}"
    vah_col = f"rvp_vah_{window_bars}"
    val_col = f"rvp_val_{window_bars}"

    result[poc_col] = np.nan
    result[vah_col] = np.nan
    result[val_col] = np.nan

    n = len(result)
    if n < window_bars or window_bars < 1:
        return result

    # Fixed global bucket grid (one grid for all windows enables incremental
    # add/subtract updates instead of a full per-window recompute).
    price_buckets, bucket_size = _global_bucket_grid(df, num_buckets)
    if price_buckets is None:
        # Degenerate price range (all bars at same price). If there is
        # volume and the window is full, the constant close IS the POC.
        if num_buckets > 0:
            flat_price = float(df["close"].iloc[0])
            flat_vals = np.full(n, np.nan)
            flat_vals[window_bars - 1:] = flat_price
            result[poc_col] = flat_vals
            result[vah_col] = flat_vals
            result[val_col] = flat_vals
        return result

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    volumes = df["volume"].to_numpy()

    running_profile = np.zeros(num_buckets)
    running_volume = 0.0
    # Ring buffer caching each in-window bar's distributed volume so the
    # bar leaving the window can be subtracted in O(buckets).
    contrib_buffer = np.zeros((window_bars, num_buckets))
    volume_buffer = np.zeros(window_bars)

    poc_vals = np.full(n, np.nan)
    vah_vals = np.full(n, np.nan)
    val_vals = np.full(n, np.nan)

    for i in range(n):
        raw_volume = volumes[i]
        bar_volume = float(raw_volume) if raw_volume > 0 else 0.0
        contrib = _distribute_bar_volume(
            float(highs[i]),
            float(lows[i]),
            float(closes[i]),
            bar_volume,
            price_buckets,
            bucket_size,
        )

        slot = i % window_bars
        if i >= window_bars:
            # Subtract the bar that just fell out of the window (stored at
            # this slot window_bars iterations ago).
            running_profile -= contrib_buffer[slot]
            running_volume -= volume_buffer[slot]

        running_profile += contrib
        running_volume += bar_volume
        contrib_buffer[slot] = contrib
        volume_buffer[slot] = bar_volume

        # Only emit a value once the window is full (matching the prior
        # behaviour, which left the first window_bars-1 bars as NaN).
        if i >= window_bars - 1 and running_volume > 0:
            extracted = _extract_poc_vah_val(
                running_profile, price_buckets, bucket_size, running_volume
            )
            if extracted is not None:
                poc, vah, val = extracted
                poc_vals[i] = poc
                vah_vals[i] = vah
                val_vals[i] = val

    result[poc_col] = poc_vals
    result[vah_col] = vah_vals
    result[val_col] = val_vals
    return result


def _global_bucket_grid(
    df: pd.DataFrame, num_buckets: int
) -> tuple[np.ndarray | None, float]:
    """Return (price_buckets, bucket_size) spanning the frame's price range.

    Returns (None, 0.0) when the price range is degenerate.
    """
    global_high = float(df["high"].max())
    global_low = float(df["low"].min())
    if global_high <= global_low:
        return None, 0.0
    buffer = (global_high - global_low) * 0.02
    price_min = global_low - buffer
    price_max = global_high + buffer
    bucket_size = (price_max - price_min) / num_buckets
    price_buckets = np.linspace(
        price_min + bucket_size / 2,
        price_max - bucket_size / 2,
        num_buckets,
    )
    return price_buckets, bucket_size


def _extract_poc_vah_val(
    profile: np.ndarray,
    price_buckets: np.ndarray,
    bucket_size: float,
    total_volume: float,
) -> tuple[float, float, float] | None:
    """Extract POC, VAH, VAL from a volume profile array.

    Returns None when there is no volume to extract from.
    """
    if total_volume <= 0:
        return None
    poc_idx = int(np.argmax(profile))
    poc = float(price_buckets[poc_idx])
    lower_idx, upper_idx, _accumulated = expand_value_area(
        profile, poc_idx, total_volume
    )
    vah = float(price_buckets[upper_idx]) + bucket_size / 2
    val = float(price_buckets[lower_idx]) - bucket_size / 2
    return poc, vah, val
