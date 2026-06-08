"""VWAP standard deviation bands — session-scoped.

Computes VWAP and its standard deviation bands (1σ, 2σ) per trading
session. Unlike pandas_ta's cumulative VWAP (which never resets), these
reset each calendar day so the bands represent intra-session fair value
and statistical extension — exactly what Auction Market Theory uses.

Adds columns: vwap_session, vwap_upper_1, vwap_lower_1,
                vwap_upper_2, vwap_lower_2
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_vwap_session_bands(df: pd.DataFrame) -> pd.DataFrame:
    """Compute session-scoped VWAP and 1σ/2σ bands.

    For each session (calendar day), computes cumulative VWAP and
    running population standard deviation of price around VWAP.
    Bands are then VWAP ± N·σ.

    Args:
        df: DataFrame with columns [high, low, close, volume]
            and a datetime index.

    Returns:
        DataFrame with added columns: vwap_session, vwap_upper_1,
        vwap_lower_1, vwap_upper_2, vwap_lower_2.
    """
    result = df.copy()

    # Typical price as the VWAP input price
    tp = (result["high"] + result["low"] + result["close"]) / 3.0

    # Initialize output columns with NaN
    for col in (
        "vwap_session",
        "vwap_upper_1",
        "vwap_lower_1",
        "vwap_upper_2",
        "vwap_lower_2",
    ):
        result[col] = np.nan

    # Group by calendar date for session-scoped computation
    date_series = pd.Series(
        pd.to_datetime(result.index).strftime("%Y-%m-%d"), index=result.index
    )

    for _date, group_idx in date_series.groupby(date_series).groups.items():
        idx = group_idx
        if len(idx) < 2:
            # Single-bar session: bands are degenerate (VWAP = tp, std = 0)
            result.loc[idx, "vwap_session"] = tp.loc[idx].values
            result.loc[idx, "vwap_upper_1"] = tp.loc[idx].values
            result.loc[idx, "vwap_lower_1"] = tp.loc[idx].values
            result.loc[idx, "vwap_upper_2"] = tp.loc[idx].values
            result.loc[idx, "vwap_lower_2"] = tp.loc[idx].values
            continue

        session_tp = tp.loc[idx].values
        session_vol = result["volume"].loc[idx].values

        # Running cumulative VWAP: sum(price * vol) / sum(vol)
        cum_pv = np.cumsum(session_tp * session_vol)
        cum_vol = np.cumsum(session_vol)

        # Avoid division by zero
        valid = cum_vol > 0
        vwap_values = np.full(len(idx), np.nan)
        vwap_values[valid] = cum_pv[valid] / cum_vol[valid]

        # Running population std of price around VWAP
        # σ²_i = Σ(p_j - VWAP_i)² / i
        #      = (Σp²_j)/i - 2·VWAP_i·(Σp_j)/i + VWAP_i²
        # Uses running sums of price and price² for O(n) computation
        cum_p = np.cumsum(session_tp)
        cum_p2 = np.cumsum(session_tp**2)
        sq_dev = np.zeros(len(idx))
        for i in range(len(idx)):
            if valid[i]:
                n = i + 1
                mean_p = cum_p[i] / n
                mean_p2 = cum_p2[i] / n
                var = mean_p2 - 2.0 * vwap_values[i] * mean_p + vwap_values[i] ** 2
                sq_dev[i] = max(var, 0.0)

        vwap_std = np.sqrt(np.maximum(sq_dev, 0.0))

        result.loc[idx, "vwap_session"] = vwap_values
        result.loc[idx, "vwap_upper_1"] = vwap_values + vwap_std
        result.loc[idx, "vwap_lower_1"] = vwap_values - vwap_std
        result.loc[idx, "vwap_upper_2"] = vwap_values + 2.0 * vwap_std
        result.loc[idx, "vwap_lower_2"] = vwap_values - 2.0 * vwap_std

    return result
