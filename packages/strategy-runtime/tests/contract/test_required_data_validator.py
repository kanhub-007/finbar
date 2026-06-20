"""Contract tests for RequiredDataValidator.

Scenario S5: RequiredDataValidator computes the same warmup/first-tradable
as finbar's current ``validate_required_data``.

The golden reference is computed inline from the enriched frame using the
same data-driven logic: the first row where all required columns are non-NaN.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
    MultiTimeframeBarEnricher,
)
from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.indicators.pandas_timeframe_bar_merger import (
    PandasTimeframeBarMerger,
)
from finbar_strategy_runtime.indicators.required_data_validator import (
    RequiredDataValidator,
)
from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[4]
_STRATEGY_YAML = (
    _REPO_ROOT
    / "strategies"
    / "intraday_scalper"
    / "14_amt_value_reject_30m_1h_mtf.yaml"
)
_DB_PATH = _REPO_ROOT / "data" / "finbar.db"


def _load_raw_bars(interval: str, limit: int | None = None) -> list[dict]:
    """Load raw OHLCV bars from the DB."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    query = (
        "SELECT timestamp, open, high, low, close, volume "
        "FROM price_bar WHERE symbol = 'SOL' AND interval = ? "
        "ORDER BY timestamp ASC"
    )
    if limit is not None:
        query += f" LIMIT {limit}"
    rows = conn.execute(query, (interval,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _parse_strategy():
    yaml_text = _STRATEGY_YAML.read_text(encoding="utf-8")
    validation = StrategyDefinitionParser().parse(yaml_text, {})
    assert validation.valid, f"Parse failed: {validation.errors}"
    return (
        validation.definition,
        list(validation.primary_required_indicators),
        dict(validation.informative_required_indicators),
        list(validation.required_columns),
    )


def _enrich_bars() -> pd.DataFrame:
    """Create an enriched MTF frame using the enricher."""
    definition, primary_req, info_req, _ = _parse_strategy()
    primary_bars = _load_raw_bars("30min")
    info_bars = {"h1": _load_raw_bars("1h")}
    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )
    return enricher.enrich(primary_bars, info_bars, definition, primary_req, info_req)


def _golden_validate(
    frame: pd.DataFrame, required_columns: list[str]
) -> dict:
    """Compute the golden reference inline (same logic as current finbar path).

    This replicates ``validate_required_data`` from finbar to avoid importing
    finbar-the-app in a package test. The RequiredDataValidator will be
    verified to match this reference.
    """
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

    # Check for unknown columns
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

    # Build numeric subset
    numeric_cols = set(frame.select_dtypes(include=["number"]).columns)
    parts = {}
    for col in required_columns:
        if col in numeric_cols:
            parts[col] = frame[col].astype(float)
        else:
            parts[col] = pd.to_numeric(frame[col], errors="coerce")
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

        if isinstance(ts, datetime):
            first_tradable = ts.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            first_tradable = str(ts)

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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def enriched_frame() -> pd.DataFrame:
    """Enriched MTF frame (module-scoped for speed)."""
    return _enrich_bars()


@pytest.fixture(scope="module")
def required_columns() -> list[str]:
    """Required columns from the production strategy parser output."""
    _, _, _, req_cols = _parse_strategy()
    return req_cols


# ---------------------------------------------------------------------------
# Scenario S5: Validator = current validate_required_data
# ---------------------------------------------------------------------------


class TestRequiredDataValidator:
    """Black-box tests for RequiredDataValidator."""

    def test_s5_validator_matches_current_path(
        self, enriched_frame, required_columns
    ):
        """Validator output equals the golden reference."""
        golden = _golden_validate(enriched_frame, required_columns)

        validator = RequiredDataValidator()
        result = validator.validate(enriched_frame, required_columns)

        assert result == golden

    def test_s5_empty_required_columns(self, enriched_frame):
        """Empty required_columns → warmup_bars=0 (everything tradable)."""
        validator = RequiredDataValidator()
        result = validator.validate(enriched_frame, [])

        assert result["warmup_bars"] == 0
        assert not result["no_tradable_bars"]
        assert result["missing_after_warmup"] == []

    def test_s5_empty_frame(self, required_columns):
        """Empty frame returns no_tradable_bars=False with warmup_bars=0."""
        empty = pd.DataFrame()
        validator = RequiredDataValidator()
        result = validator.validate(empty, required_columns)

        assert result["warmup_bars"] == 0
        assert not result["no_tradable_bars"]
        assert result["missing_after_warmup"] == []

    def test_s5_column_never_valid(self, enriched_frame, required_columns):
        """Column that is always NaN → no_tradable_bars=True."""
        frame = enriched_frame.copy()
        frame["always_nan"] = np.nan
        cols = required_columns + ["always_nan"]

        validator = RequiredDataValidator()
        result = validator.validate(frame, cols)

        # With an always-NaN column, no row can be fully valid
        assert result["no_tradable_bars"]
        # The always-NaN column or other columns should appear in diagnostics
        assert len(result["missing_after_warmup"]) > 0
