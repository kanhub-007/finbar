"""Tests for the rolling-window Volume Profile (rvp_*).

Covers the incremental implementation: correctness against a brute-force
computation on the same global bucket grid, NaN warmup, and the stability
of expand_value_area under floating-point perturbation.
"""

import numpy as np
import pandas as pd
import pytest

from finbar.core.domain.services._profile_utils import expand_value_area
from finbar.core.domain.services.volume_profile import (
    _distribute_bar_volume,
    _extract_poc_vah_val,
    _global_bucket_grid,
    compute_rolling_window_vp,
)


def _frame(n=120, seed=7):
    rng = np.random.default_rng(seed)
    prices = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    return pd.DataFrame(
        {
            "high": prices + 0.5,
            "low": prices - 0.5,
            "close": prices,
            "volume": rng.integers(100, 1000, n).astype(float),
        }
    )


def _brute_force(df, window_bars, num_buckets):
    """Independent reference: fresh per-window sum on the global grid."""
    buckets, bsize = _global_bucket_grid(df, num_buckets)
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    v = df["volume"].to_numpy()
    n = len(df)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    for i in range(window_bars - 1, n):
        prof = np.zeros(num_buckets)
        tot = 0.0
        for j in range(i - window_bars + 1, i + 1):
            bv = float(v[j]) if v[j] > 0 else 0.0
            prof += _distribute_bar_volume(
                float(h[j]), float(lo[j]), float(c[j]), bv, buckets, bsize
            )
            tot += bv
        e = _extract_poc_vah_val(prof, buckets, bsize, tot)
        if e is not None:
            poc[i], vah[i], val[i] = e
    return poc, vah, val


class TestRollingWindowVolumeProfile:
    def test_first_window_minus_one_bars_are_nan(self):
        df = _frame(n=30)
        wb = 10
        res = compute_rolling_window_vp(df, window_bars=wb, num_buckets=50)
        poc = res[f"rvp_poc_{wb}"].to_numpy()
        assert np.all(np.isnan(poc[: wb - 1]))
        assert not np.isnan(poc[wb - 1])

    def test_matches_brute_force_on_global_grid(self):
        df = _frame(n=120)
        wb = 10
        res = compute_rolling_window_vp(df, window_bars=wb, num_buckets=50)
        poc_e, vah_e, val_e = _brute_force(df, wb, 50)
        poc = res[f"rvp_poc_{wb}"].to_numpy()
        vah = res[f"rvp_vah_{wb}"].to_numpy()
        val = res[f"rvp_val_{wb}"].to_numpy()
        assert np.allclose(poc, poc_e, equal_nan=True)
        assert np.allclose(vah, vah_e, equal_nan=True)
        assert np.allclose(val, val_e, equal_nan=True)

    def test_poc_within_price_range_and_vah_above_val(self):
        df = _frame(n=60)
        wb = 8
        res = compute_rolling_window_vp(df, window_bars=wb, num_buckets=40)
        poc = res[f"rvp_poc_{wb}"].dropna()
        vah = res[f"rvp_vah_{wb}"].dropna()
        val = res[f"rvp_val_{wb}"].dropna()
        assert (poc >= df["low"].min() - 1).all()
        assert (poc <= df["high"].max() + 1).all()
        assert (vah >= val).all()

    def test_too_few_bars_returns_all_nan(self):
        df = _frame(n=5)
        res = compute_rolling_window_vp(df, window_bars=48, num_buckets=50)
        assert res["rvp_poc_48"].isna().all()

    def test_zero_volume_frame_does_not_crash(self):
        df = _frame(n=30)
        df["volume"] = 0.0
        res = compute_rolling_window_vp(df, window_bars=10, num_buckets=50)
        # No volume -> no POC extractable -> all NaN.
        assert res["rvp_poc_10"].isna().all()


class TestExpandValueAreaStability:
    def test_tiny_perturbation_does_not_flip_value_area(self):
        """Regression: expand_value_area was chaotic — a 1e-13 perturbation
        could flip the greedy side choice and cascade into a wildly different
        value area. With a relative tolerance, the result must be stable."""
        rng = np.random.default_rng(3)
        profile = rng.random(50) * 100
        poc_idx = int(np.argmax(profile))
        total = float(profile.sum())
        lo, up, acc = expand_value_area(profile, poc_idx, total)
        # Perturb by floating-point-scale noise.
        noisy = profile + np.finfo(float).eps * profile
        lo2, up2, acc2 = expand_value_area(noisy, poc_idx, total)
        assert (lo, up) == (lo2, up2)
        assert acc == pytest.approx(acc2, rel=1e-9)

    def test_clear_peak_expands_to_value_area(self):
        profile = np.zeros(20)
        profile[10] = 100.0
        profile[9] = 30.0
        profile[11] = 30.0
        lo, up, acc = expand_value_area(profile, 10, float(profile.sum()))
        # POC at 10; ties expand upward, so the first step goes to 11,
        # capturing 130/160 = 81% which already exceeds the 68% target.
        assert lo <= 10 <= up
        assert up == 11
        assert acc == pytest.approx(130.0)
