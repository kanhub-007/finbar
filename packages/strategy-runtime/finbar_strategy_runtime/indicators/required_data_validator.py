"""RequiredDataValidator — data-driven warmup/readiness for an enriched frame.

Returns warmup_bars, first_tradable, missing_after_warmup, no_tradable_bars
— identical to finbar's current ``validate_required_data``.

Shared so finbot stops gating on a fixed ``min_bars`` and stops skipping
warmup bars entirely.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


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
            Dict with keys:
                warmup_bars: int — index of first tradable row.
                first_tradable: str — timestamp of first tradable row.
                skipped_bars_due_to_warmup: int — same as warmup_bars.
                skipped_bars_due_to_missing: int — bars skipped after warmup.
                missing_after_warmup: list[str] — columns still missing.
                no_tradable_bars: bool — True if no row is fully valid.
        """
        bars = len(frame)
        missing_after_warmup: list[str] = []
        warmup_bars = 0
        first_tradable = ""

        if not required_columns or bars == 0:
            return {
                "warmup_bars": 0,
                "first_tradable": "",
                "skipped_bars_due_to_warmup": 0,
                "skipped_bars_due_to_missing": 0,
                "missing_after_warmup": [],
                "no_tradable_bars": False,
            }

        unknown = [
            col for col in required_columns if col not in frame.columns
        ]
        if unknown:
            return {
                "warmup_bars": 0,
                "first_tradable": "",
                "skipped_bars_due_to_warmup": 0,
                "skipped_bars_due_to_missing": bars,
                "missing_after_warmup": unknown,
                "no_tradable_bars": True,
            }

        subset = self._to_numeric_subset(frame, required_columns)
        valid_mask = subset.notna().all(axis=1)

        first_valid_idx = valid_mask.idxmax() if valid_mask.any() else None
        if first_valid_idx is not None:
            warmup_bars = frame.index.get_loc(first_valid_idx)
            ts = frame.index[warmup_bars]
            if isinstance(ts, datetime):
                first_tradable = ts.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                first_tradable = str(ts)

            post_mask = valid_mask.iloc[warmup_bars:]
            if not post_mask.all():
                for column in required_columns:
                    col_valid = (
                        subset[column].iloc[warmup_bars:].notna()
                    )
                    if not col_valid.all():
                        missing_after_warmup.append(column)
        else:
            warmup_bars = bars
            never_valid = [
                col
                for col in required_columns
                if subset[col].notna().sum() == 0
            ]
            missing_after_warmup = never_valid

        no_tradable = warmup_bars >= bars
        skipped_missing = 0
        if missing_after_warmup:
            col_subset = subset[missing_after_warmup]
            skipped_missing = int(
                col_subset.iloc[warmup_bars:].isna().any(axis=1).sum()
            )

        return {
            "warmup_bars": warmup_bars,
            "first_tradable": first_tradable,
            "skipped_bars_due_to_warmup": warmup_bars,
            "skipped_bars_due_to_missing": skipped_missing,
            "missing_after_warmup": missing_after_warmup,
            "no_tradable_bars": no_tradable,
        }

    @staticmethod
    def _to_numeric_subset(
        frame: pd.DataFrame, columns: list[str]
    ) -> pd.DataFrame:
        """Return a numeric-only subset, skipping coercion for float columns.

        Most columns in an enriched frame are already float64 (from
        pandas_ta). Calling pd.to_numeric on them is a no-op copy that
        wastes time on large frames.
        """
        numeric_cols = set(frame.select_dtypes(include=["number"]).columns)
        parts: dict[str, pd.Series] = {}
        for col in columns:
            if col in numeric_cols:
                parts[col] = frame[col].astype(float)
            else:
                parts[col] = pd.to_numeric(frame[col], errors="coerce")
        return pd.DataFrame(parts, index=frame.index)
