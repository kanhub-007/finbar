"""PandasSignalCalculator - pandas implementation of SignalCalculator.

Computes signal interpretation columns from enriched OHLCV DataFrames.
Uses the ConfidenceScorer domain service for pure scoring logic.
"""

from __future__ import annotations

import pandas as pd

from finbar_strategy_runtime.domain.entities.risk_factor import RiskFactor
from finbar_strategy_runtime.domain.entities.rsi_zone import RsiZone
from finbar_strategy_runtime.domain.interfaces.signal_calculator import SignalCalculator
from finbar_strategy_runtime.domain.services.confidence_scorer import ConfidenceScorer


class PandasSignalCalculator(SignalCalculator):
    """Add signal interpretation columns to a pandas DataFrame."""

    def __init__(self, scorer: ConfidenceScorer | None = None):
        """Create the calculator with an optional domain scorer."""
        self._scorer = scorer or ConfidenceScorer()

    def calculate(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Compute all signal columns and return the enriched frame."""
        result = frame.copy()
        result["rsi_zone"] = self._compute_rsi_zone(result)
        result["is_extreme_oversold"] = result["rsi_zone"] == RsiZone.EXTREME_OVERSOLD
        result["is_extreme_overbought"] = (
            result["rsi_zone"] == RsiZone.EXTREME_OVERBOUGHT
        )
        result["is_overextended"] = (
            result["is_extreme_oversold"] | result["is_extreme_overbought"]
        )
        result["adx_conviction"] = self._compute_adx_conviction(result)
        result["is_weak_trend"] = result.get("adx", 0) < 20
        result["is_squeeze"] = self._compute_squeeze(result)
        result["near_resistance"] = self._compute_near_resistance(result)
        result["near_support"] = self._compute_near_support(result)
        result["is_low_volume"] = result.get("rvol", 1.0) < 0.5
        result["confidence_score"] = self._compute_confidence(result)
        return result

    # ── column calculators ────────────────────────────────────────────

    @staticmethod
    def _compute_rsi_zone(df: pd.DataFrame) -> pd.Series:
        rsi = df.get("rsi_14", pd.Series(50, index=df.index))
        conditions = [
            (rsi < 20, RsiZone.EXTREME_OVERSOLD),
            (rsi < 30, RsiZone.OVERSOLD),
            (rsi <= 70, RsiZone.NEUTRAL),
            (rsi <= 80, RsiZone.OVERBOUGHT),
        ]
        # Default is EXTREME_OVERBOUGHT to handle rsi > 80 (not covered by
        # the explicit conditions). After classification, NaN RSI values
        # are reset to NEUTRAL (all comparisons with NaN are False, so
        # without this guard NaN would inherit the default).
        result = pd.Series(RsiZone.EXTREME_OVERBOUGHT, index=df.index, dtype="object")
        for cond, zone in reversed(conditions):
            result = result.where(~cond, zone)
        result = result.where(~rsi.isna(), RsiZone.NEUTRAL)
        return result

    @staticmethod
    def _compute_adx_conviction(df: pd.DataFrame) -> pd.Series:
        adx = df.get("adx", pd.Series(0, index=df.index))
        conditions = [
            (adx < 15, 20),
            (adx < 20, 35),
            (adx < 25, 50),
            (adx < 35, 70),
            (adx < 50, 85),
        ]
        result = pd.Series(95, index=df.index, dtype="float64")
        for cond, val in reversed(conditions):
            result = result.where(~cond, float(val))
        return result

    @staticmethod
    def _compute_squeeze(df: pd.DataFrame) -> pd.Series:
        bb_upper = df.get("bb_upper_20")
        bb_lower = df.get("bb_lower_20")
        adx = df.get("adx")
        close = df.get("close")
        if bb_upper is None or bb_lower is None or adx is None or close is None:
            return pd.Series(False, index=df.index)
        bb_width_pct = (bb_upper - bb_lower) / close.replace(0, pd.NA)
        return (bb_width_pct < 0.03) & (adx < 20)

    @staticmethod
    def _compute_near_resistance(df: pd.DataFrame) -> pd.Series:
        close = df.get("close")
        swing_high = df.get("swing_high_20")
        atr = df.get("atr")
        if close is None or swing_high is None or atr is None:
            return pd.Series(False, index=df.index)
        valid = (swing_high > 0) & (atr > 0)
        distance = (close - swing_high).abs()
        return valid & (distance < 0.5 * atr)

    @staticmethod
    def _compute_near_support(df: pd.DataFrame) -> pd.Series:
        close = df.get("close")
        swing_low = df.get("swing_low_20")
        atr = df.get("atr")
        if close is None or swing_low is None or atr is None:
            return pd.Series(False, index=df.index)
        valid = (swing_low > 0) & (atr > 0)
        distance = (close - swing_low).abs()
        return valid & (distance < 0.5 * atr)

    def _compute_confidence(self, df: pd.DataFrame) -> pd.Series:
        """Row-wise confidence scoring.

        The ConfidenceScorer is a pure domain service (not pandas-aware), so it
        is called once per row. To keep this affordable on large intraday frames
        (~30k rows), the needed columns are extracted to numpy arrays ONCE and
        indexed by position inside the loop, avoiding a per-row pd.Series
        allocation via df.iloc[i] and the repeated row.get() dict lookups.
        """

        n = len(df)
        if n == 0:
            return pd.Series([], index=df.index, dtype="float64")

        adx = self._numcol(df, "adx", 0.0)
        rsi = self._numcol(df, "rsi_14", 50.0)
        rvol = self._numcol(df, "rvol", 1.0)
        direction = self._objcol(df, "trend_direction")
        is_power_zone = self._boolcol(df, "is_power_zone")
        near_resistance = self._boolcol(df, "near_resistance")
        near_support = self._boolcol(df, "near_support")
        is_squeeze = self._boolcol(df, "is_squeeze")

        scores: list[int] = []
        for i in range(n):
            # Coalesce only NaN (missing/insufficient data) to the neutral
            # default; a legitimate 0.0 must be preserved. The previous
            # `value or default` collapsed 0.0 into the default, which hid an
            # extreme RSI of 0 (treated as neutral 50) and a genuine zero
            # relative volume (treated as normal 1.0).
            adx_i = _coalesce_nan(adx[i], 0.0)
            rsi_i = _coalesce_nan(rsi[i], 50.0)
            rvol_i = _coalesce_nan(rvol[i], 1.0)
            risk_factors = self._gather_risk_factors(
                adx_i,
                rsi_i,
                rvol_i,
                bool(near_resistance[i]),
                bool(near_support[i]),
                bool(is_squeeze[i]),
            )
            result = self._scorer.score(
                adx=adx_i,
                direction=str(direction[i]),
                rvol=rvol_i,
                is_power_zone=bool(is_power_zone[i]),
                risk_factors=risk_factors,
            )
            scores.append(result.score)
        return pd.Series(scores, index=df.index, dtype="float64")

    @staticmethod
    def _numcol(df: pd.DataFrame, name: str, default: float):
        import numpy as np

        series = df.get(name)
        if series is None:
            return np.full(len(df), default, dtype="float64")
        return series.to_numpy(dtype="float64")

    @staticmethod
    def _boolcol(df: pd.DataFrame, name: str):
        import numpy as np

        series = df.get(name)
        if series is None:
            return np.zeros(len(df), dtype="bool")
        # to_numpy(dtype=bool) converts NaN->True, matching bool(float('nan'))
        # in the previous per-row implementation.
        return series.to_numpy(dtype="bool")

    @staticmethod
    def _objcol(df: pd.DataFrame, name: str):
        import numpy as np

        series = df.get(name)
        if series is None:
            return np.array([""] * len(df), dtype=object)
        return series.to_numpy(dtype=object)

    @staticmethod
    def _gather_risk_factors(
        adx: float,
        rsi: float,
        rvol: float,
        near_resistance: bool,
        near_support: bool,
        is_squeeze: bool,
    ) -> list[str]:
        factors: list[str] = []
        if adx < 20:
            factors.append(RiskFactor.WEAK_TREND)
        if rvol < 0.5:
            factors.append(RiskFactor.LOW_VOLUME)
        if rsi > 80:
            factors.append(RiskFactor.OVEREXTENDED_UP)
        elif rsi < 20:
            factors.append(RiskFactor.OVEREXTENDED_DOWN)
        if near_resistance:
            factors.append(RiskFactor.NEAR_RESISTANCE)
        if near_support:
            factors.append(RiskFactor.NEAR_SUPPORT)
        if is_squeeze:
            factors.append(RiskFactor.BB_SQUEEZE)
        return factors


def _coalesce_nan(value, default: float) -> float:
    """Return ``value`` unless it is NaN, in which case return ``default``.

    Unlike ``value or default``, this preserves a legitimate ``0.0`` (which is
    falsy) and only substitutes the default for missing data.
    """
    import numpy as np

    if np.isnan(value):
        return default
    return float(value)
