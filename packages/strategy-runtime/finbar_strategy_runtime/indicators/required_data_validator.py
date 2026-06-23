"""RequiredDataValidator — data-driven warmup/readiness for an enriched frame.

Returns warmup_bars, first_tradable, missing_after_warmup, no_tradable_bars
— identical to finbar's current ``validate_required_data``.

Shared so finbot stops gating on a fixed ``min_bars`` and stops skipping
warmup bars entirely.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from finbar_strategy_runtime.domain.entities.warmup_validation_result import (
    WarmupValidationResult,
)


class RequiredDataValidator:
    """Data-driven warmup/readiness for an enriched frame.

    Determines the first row where all required columns are non-NaN
    (warmup_bars, first_tradable) and reports any columns that have
    missing values after that point.
    """

    def validate(
        self,
        frame: pd.DataFrame,
        required_columns: list[str],
    ) -> dict:
        """Check that strategy-required columns are valid after warmup.

        Args:
            frame: An enriched DataFrame with indicator and feature columns.
            required_columns: Column names the strategy needs to evaluate.

        Returns:
            ``WarmupValidationResult`` (call ``.to_dict()`` for the legacy
            dict shape).
        """
        bars = len(frame)

        if not required_columns or bars == 0:
            return WarmupValidationResult(
                warmup_bars=0,
                first_tradable="",
                skipped_bars_due_to_warmup=0,
                skipped_bars_due_to_missing=0,
            )

        unknown = [c for c in required_columns if c not in frame.columns]
        if unknown:
            return WarmupValidationResult(
                warmup_bars=0,
                first_tradable="",
                skipped_bars_due_to_warmup=0,
                skipped_bars_due_to_missing=bars,
                missing_after_warmup=unknown,
                no_tradable_bars=True,
            )

        return self._validate_present(frame, required_columns, bars)

    def _validate_present(
        self,
        frame: pd.DataFrame,
        required_columns: list[str],
        bars: int,
    ) -> WarmupValidationResult:
        """Validate a frame where all required columns are present."""
        subset = self._to_numeric_subset(frame, required_columns)
        valid_mask = subset.notna().all(axis=1)

        if not valid_mask.any():
            never_valid = [
                c for c in required_columns
                if subset[c].notna().sum() == 0
            ]
            return WarmupValidationResult(
                warmup_bars=bars,
                first_tradable="",
                skipped_bars_due_to_warmup=bars,
                skipped_bars_due_to_missing=0,
                missing_after_warmup=never_valid,
                no_tradable_bars=True,
            )

        first_valid_idx = valid_mask.idxmax()
        warmup_bars = frame.index.get_loc(first_valid_idx)
        ts = frame.index[warmup_bars]
        first_tradable = (
            ts.strftime("%Y-%m-%dT%H:%M:%S")
            if isinstance(ts, datetime)
            else str(ts)
        )

        missing_after_warmup = self._columns_missing_after(
            subset, required_columns, warmup_bars
        )
        skipped_missing = self._count_skipped(
            subset, missing_after_warmup, warmup_bars
        )
        return WarmupValidationResult(
            warmup_bars=warmup_bars,
            first_tradable=first_tradable,
            skipped_bars_due_to_warmup=warmup_bars,
            skipped_bars_due_to_missing=skipped_missing,
            missing_after_warmup=missing_after_warmup,
            no_tradable_bars=warmup_bars >= bars,
        )

    @staticmethod
    def _columns_missing_after(
        subset: pd.DataFrame,
        required_columns: list[str],
        warmup_bars: int,
    ) -> list[str]:
        """Return required columns that still have NaN values after warmup."""
        missing: list[str] = []
        tail = subset.iloc[warmup_bars:]
        if tail.notna().all(axis=1).all():
            return missing
        for column in required_columns:
            if not tail[column].notna().all():
                missing.append(column)
        return missing

    @staticmethod
    def _count_skipped(
        subset: pd.DataFrame,
        missing_after_warmup: list[str],
        warmup_bars: int,
    ) -> int:
        """Count bars after warmup that are non-tradable due to missing cols."""
        if not missing_after_warmup:
            return 0
        return int(
            subset[missing_after_warmup]
            .iloc[warmup_bars:]
            .isna()
            .any(axis=1)
            .sum()
        )

    @staticmethod
    def _to_numeric_subset(
        frame: pd.DataFrame, columns: list[str]
    ) -> pd.DataFrame:
        """Return a numeric-only subset, avoiding unnecessary copies.

        Already-numeric columns (float64 from pandas_ta) are kept as-is
        in a single slice copy. Only non-numeric columns are coerced via
        ``pd.to_numeric``.
        """
        numeric_cols = set(frame.select_dtypes(include=["number"]).columns)
        subset = frame[columns].copy()
        for col in columns:
            if col not in numeric_cols:
                subset[col] = pd.to_numeric(subset[col], errors="coerce")
        return subset
