"""Contract tests for RequiredDataValidator.

Scenario S5: RequiredDataValidator computes the same warmup/first-tradable
as finbar's current ``validate_required_data``.

The golden reference is computed inline from the enriched frame using the
same data-driven logic: the first row where all required columns are non-NaN.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.required_data_validator import (
    RequiredDataValidator,
)

from .conftest import needs_finbar_data


def _golden_validate(
    frame: pd.DataFrame, required_columns: list[str]
) -> dict:
    """Compute the golden reference inline (same logic as current finbar path)."""
    bars = len(frame)

    if not required_columns or bars == 0:
        return {
            "warmup_bars": 0,
            "first_tradable": "",
            "skipped_bars_due_to_warmup": 0,
            "skipped_bars_due_to_missing": 0,
            "missing_after_warmup": [],
            "no_tradable_bars": False,
        }

    unknown = [c for c in required_columns if c not in frame.columns]
    if unknown:
        return {
            "warmup_bars": 0,
            "first_tradable": "",
            "skipped_bars_due_to_warmup": 0,
            "skipped_bars_due_to_missing": bars,
            "missing_after_warmup": unknown,
            "no_tradable_bars": True,
        }

    numeric_cols = set(frame.select_dtypes(include=["number"]).columns)
    parts = {}
    for col in required_columns:
        parts[col] = (
            frame[col].astype(float)
            if col in numeric_cols
            else pd.to_numeric(frame[col], errors="coerce")
        )
    subset = pd.DataFrame(parts, index=frame.index)

    valid_mask = subset.notna().all(axis=1)
    warmup_bars = 0
    first_tradable = ""
    missing_after_warmup: list[str] = []

    if valid_mask.any():
        first_valid_idx = valid_mask.idxmax()
        warmup_bars = frame.index.get_loc(first_valid_idx)
        ts = frame.index[warmup_bars]
        from datetime import datetime

        first_tradable = (
            ts.strftime("%Y-%m-%dT%H:%M:%S")
            if isinstance(ts, datetime)
            else str(ts)
        )

        post_mask = valid_mask.iloc[warmup_bars:]
        if not post_mask.all():
            for column in required_columns:
                col_valid = subset[column].iloc[warmup_bars:].notna()
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


# ---------------------------------------------------------------------------
# Scenario S5: Validator = current validate_required_data
# ---------------------------------------------------------------------------


@needs_finbar_data
class TestRequiredDataValidator:
    """Black-box tests for RequiredDataValidator."""

    def test_s5_validator_matches_current_path(
        self, enriched_mtf_frame, strategy_context
    ):
        _, _, _, required_columns = strategy_context
        golden = _golden_validate(enriched_mtf_frame, required_columns)

        validator = RequiredDataValidator()
        result = validator.validate(enriched_mtf_frame, required_columns)

        assert result == golden

    def test_s5_empty_required_columns(self, enriched_mtf_frame):
        validator = RequiredDataValidator()
        result = validator.validate(enriched_mtf_frame, [])

        assert result["warmup_bars"] == 0
        assert not result["no_tradable_bars"]
        assert result["missing_after_warmup"] == []

    def test_s5_empty_frame(self, strategy_context):
        _, _, _, required_columns = strategy_context
        empty = pd.DataFrame()
        validator = RequiredDataValidator()
        result = validator.validate(empty, required_columns)

        assert result["warmup_bars"] == 0
        assert not result["no_tradable_bars"]
        assert result["missing_after_warmup"] == []

    def test_s5_column_never_valid(self, enriched_mtf_frame, strategy_context):
        _, _, _, required_columns = strategy_context
        frame = enriched_mtf_frame.copy()
        frame["always_nan"] = np.nan
        cols = required_columns + ["always_nan"]

        validator = RequiredDataValidator()
        result = validator.validate(frame, cols)

        assert result["no_tradable_bars"]
        assert len(result["missing_after_warmup"]) > 0
