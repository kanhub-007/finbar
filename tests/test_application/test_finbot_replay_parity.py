"""Finbot replay parity contract for package causal enrichment.

Scenario 15: Finbar's causal backtest frame and a Finbot-style closed-candle
replay through the package enricher produce identical enriched rows and signal
timestamps for the SOL parity fixtures and production strategy.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
)
from finbar_strategy_runtime.indicators import (
    causal_multi_timeframe_streaming_enricher as causal_mtf,
)

from finbar.core.application.live_parity_frame_builder import build_causal_frame
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARITY_DIR = (
    _REPO_ROOT
    / "packages"
    / "strategy-runtime"
    / "tests"
    / "fixtures"
    / "parity"
)
_PRIMARY_CSV = _PARITY_DIR / "sol_30min.csv"
_INFO_CSV = _PARITY_DIR / "sol_1h.csv"
_STRATEGY_YAML = (
    _REPO_ROOT
    / "strategies"
    / "intraday_scalper"
    / "14_amt_value_reject_30m_1h_mtf.yaml"
)

needs_parity_assets = pytest.mark.skipif(
    not _PRIMARY_CSV.exists() or not _INFO_CSV.exists() or not _STRATEGY_YAML.exists(),
    reason="SOL parity fixtures or production strategy not found",
)


def _load_bars(path: Path) -> list[dict]:
    """Load fixture bars as API-style dictionaries."""
    frame = pd.read_csv(path)
    return frame.to_dict(orient="records")


def _parse_strategy():
    """Parse the production strategy and return validation metadata."""
    validation = StrategyDefinitionParser().parse(
        _STRATEGY_YAML.read_text(encoding="utf-8")
    )
    assert validation.valid is True, validation.errors
    assert validation.definition is not None
    return validation


def _package_replay_rows(validation, primary: list[dict], info: dict[str, list[dict]]):
    """Replay closed candles through the package enricher like Finbot would."""
    factory = causal_mtf.CausalMultiTimeframeStreamingEnricher
    enricher = factory.from_strategy_definition(
        validation.definition,
        validation.primary_required_indicators,
        validation.informative_required_indicators,
    )
    info_ptrs = {alias: 0 for alias in info}
    rows: list[dict] = []
    for bar in primary:
        primary_open = pd.Timestamp(bar["timestamp"], unit="s", tz="UTC")
        for alias, ibars in info.items():
            while info_ptrs[alias] < len(ibars):
                candidate = ibars[info_ptrs[alias]]
                candidate_open = pd.Timestamp(
                    candidate["timestamp"],
                    unit="s",
                    tz="UTC",
                )
                if candidate_open <= primary_open:
                    emitted = enricher.update(alias, candidate)
                    assert emitted is None
                    info_ptrs[alias] += 1
                else:
                    break
        latest = enricher.update("primary", bar)
        assert latest is not None
        rows.append(latest.values)
    return rows


def _frame_rows(frame: pd.DataFrame) -> list[dict]:
    """Convert Finbar causal frame rows to package-style row dictionaries."""
    rows = []
    for timestamp, row in frame.iterrows():
        values = row.to_dict()
        values["timestamp"] = int(pd.Timestamp(timestamp).timestamp())
        rows.append(values)
    return rows


def _assert_rows_equivalent(left: list[dict], right: list[dict]) -> None:
    """Assert two enriched row sequences are equivalent by value."""
    assert len(left) == len(right)
    for row_index, (lrow, rrow) in enumerate(zip(left, right, strict=True)):
        assert set(lrow) == set(rrow), f"row {row_index} columns differ"
        for key in sorted(lrow):
            _assert_value_equivalent(lrow[key], rrow[key], f"row {row_index} {key}")


def _assert_value_equivalent(left: Any, right: Any, label: str) -> None:
    """Compare scalar metric values with NaN and numeric tolerance support."""
    if _is_nan(left) and _is_nan(right):
        return
    if isinstance(left, bool) or isinstance(right, bool):
        assert bool(left) == bool(right), label
        return
    try:
        lnum = float(left)
        rnum = float(right)
    except (TypeError, ValueError):
        assert left == right, f"{label}: {left!r} != {right!r}"
        return
    assert math.isclose(lnum, rnum, rel_tol=1e-9, abs_tol=1e-12), (
        f"{label}: {lnum!r} != {rnum!r}"
    )


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def _signal_timestamps(definition, rows: list[dict]) -> list[Any]:
    """Return timestamps where the JSON strategy emits a non-hold signal."""
    strategy = JsonRuleBasedStrategy(definition)
    position = {"direction": "", "size": 0}
    timestamps = []
    for row in rows:
        signal = strategy.on_bar(row, position)
        if signal.action != "hold":
            timestamps.append(row["timestamp"])
            position = {"direction": signal.direction, "size": 1}
    return timestamps


@needs_parity_assets
class TestFinbotReplayParity:
    """Black-box parity tests for Finbar frame builder vs package replay."""

    def test_package_replay_rows_match_finbar_causal_rows(self):
        """Finbot-style replay receives identical enriched rows and signals."""
        validation = _parse_strategy()
        primary = _load_bars(_PRIMARY_CSV)[:120]
        info = {"h1": _load_bars(_INFO_CSV)[:140]}

        finbar_frame = build_causal_frame(
            primary_bars=primary,
            informative_bars=info,
            definition=validation.definition,
            primary_required_indicators=validation.primary_required_indicators,
            informative_required_indicators=validation.informative_required_indicators,
        )
        finbar_rows = _frame_rows(finbar_frame)
        finbot_rows = _package_replay_rows(validation, primary, info)

        _assert_rows_equivalent(finbot_rows, finbar_rows)
        finbot_signal_times = _signal_timestamps(validation.definition, finbot_rows)
        finbar_signal_times = _signal_timestamps(validation.definition, finbar_rows)
        assert finbot_signal_times == finbar_signal_times
