"""Tests for BacktestStrategyDefinitionUseCase live-parity enrichment mode.

Scenario 3 (finbar wiring): when ``enrichment_mode="live_parity_streaming"``,
the backtest builds each bar's enriched row from the package
``CausalMultiTimeframeStreamingEnricher`` (causal), so the result matches
the streaming-prefix reference and differs from the legacy
``batch_full_frame`` mode for frame-dependent VP/AMT strategies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
    MultiTimeframeBarEnricher,
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

from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.domain.entities.execution_config import ExecutionConfig
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_DIR = _REPO_ROOT / "packages" / "strategy-runtime" / "tests" / "fixtures" / "parity"
_STRATEGY_YAML = (
    _REPO_ROOT
    / "strategies"
    / "intraday_scalper"
    / "14_amt_value_reject_30m_1h_mtf.yaml"
)

needs_finbar_data = pytest.mark.skipif(
    not _STRATEGY_YAML.exists() or not _FIXTURES_DIR.exists(),
    reason="Finbar fixtures not found",
)


def _load_bars(interval: str, limit: int | None = None) -> list[dict]:
    """Load committed parity fixture bars (stable, not live-DB-dependent)."""
    import csv

    mapping = {"30min": "sol_30min.csv", "1h": "sol_1h.csv"}
    filename = mapping.get(interval)
    if filename is None:
        raise ValueError(f"No fixture for interval: {interval}")
    path = _FIXTURES_DIR / filename
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit is not None and limit < len(rows):
        rows = rows[-limit:]
    return [{k: float(v) if k != "timestamp" else int(v) for k, v in r.items()} for r in rows]


def _make_use_case() -> BacktestStrategyDefinitionUseCase:
    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )
    return BacktestStrategyDefinitionUseCase(
        engine=BacktestRunner(),
        converter=PandasBarFrameConverter(),
        strategy_factory=StrategyDefinitionFactory(),
        parser=StrategyDefinitionParser(),
        enricher=enricher,
    )


def _request(bars, info, mode) -> BacktestStrategyDefinitionRequest:
    return BacktestStrategyDefinitionRequest(
        definition=_STRATEGY_YAML.read_text(encoding="utf-8"),
        bars=bars,
        informative_bars=info,
        # SOL is crypto; crypto_24_7 calendar matches 48 bars/day (30min).
        execution=ExecutionConfig(market_calendar="crypto_24_7"),
        symbol="SOL",
        interval="30min",
        enrichment_mode=mode,
    )


@needs_finbar_data
class TestBacktestLiveParityMode:
    """Black-box: live_parity_streaming mode produces causal results."""

    def test_live_parity_and_batch_first_trades_differ(self):
        """Live-parity and batch first trades differ (VP-broadcast defect proof).

        Under the strict warmup contract (spec 2026-06-23 Scenario 4),
        ``poc_slope_5`` is NaN until 5 sessions exist, so the first signal
        on both paths has moved past warmup. The invariant is that the two
        paths produce DIFFERENT first trades — the completed-session VP
        broadcast still leaks future data into earlier rows in batch mode.
        """
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        use_case = _make_use_case()

        live = use_case.execute(_request(bars, info, "live_parity_streaming"))
        batch = use_case.execute(_request(bars, info, "batch_full_frame"))

        assert live.valid and live.result is not None
        assert batch.valid and batch.result is not None
        assert live.result.trades, "Live-parity mode produced no trades"
        assert batch.result.trades, "Batch mode produced no trades"

        live_first = live.result.trades[0]
        batch_first = batch.result.trades[0]
        assert (
            live_first["entry_date"] != batch_first["entry_date"]
            or live_first["direction"] != batch_first["direction"]
        ), (
            f"Live {live_first} and batch {batch_first} must differ"
        )

    def test_live_parity_first_trade_is_short(self):
        """Live-parity first trade is a short entry (causal path bias)."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        use_case = _make_use_case()

        live = use_case.execute(_request(bars, info, "live_parity_streaming"))
        assert live.valid and live.result is not None
        assert live.result.trades
        assert live.result.trades[0]["metadata"]["direction"] == "short"

    def test_batch_mode_produces_trades(self):
        """Batch mode produces trades — the defect is documented by differing
        from live parity (see test above), not by a specific row number."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        use_case = _make_use_case()

        batch = use_case.execute(_request(bars, info, "batch_full_frame"))
        assert batch.valid and batch.result is not None
        assert batch.result.trades, "Batch mode produced no trades"


@needs_finbar_data
class TestBacktestParityMetadata:
    """Scenario 6: batch mode labelled non-live-parity for frame-dependent
    indicators; live-parity mode marked safe."""

    def test_batch_frame_dependent_marked_not_live_parity_safe(self):
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        result = _make_use_case().execute(_request(bars, info, "batch_full_frame"))
        assert result.valid and result.result is not None

        assert result.result.enrichment_mode == "batch_full_frame"
        assert result.result.live_parity_safe is False
        warning_text = " ".join(result.result.parity_warnings).lower()
        assert (
            "vp_poc" in warning_text or "vp_vah" in warning_text
        ), f"Warnings should name vp_poc/vp_vah/vp_val: {result.result.parity_warnings}"

    def test_live_parity_mode_marked_safe(self):
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        result = _make_use_case().execute(_request(bars, info, "live_parity_streaming"))
        assert result.valid and result.result is not None

        assert result.result.enrichment_mode == "live_parity_streaming"
        assert result.result.live_parity_safe is True

    def test_batch_without_frame_dependent_indicators_is_safe(self):
        """A strategy with no frame-dependent indicators is safe even in batch."""
        from tests.test_application.test_strategy_json_sdk import (
            _sma_strategy,
        )

        bars = _load_bars("30min", 200)
        request = BacktestStrategyDefinitionRequest(
            definition=_sma_strategy(),
            bars=bars,
            execution=ExecutionConfig(),
            symbol="SOL",
            interval="30min",
            enrichment_mode="batch_full_frame",
        )
        result = _make_use_case().execute(request)
        assert result.valid and result.result is not None, result.errors

        assert result.result.enrichment_mode == "batch_full_frame"
        assert result.result.live_parity_safe is True


@needs_finbar_data
class TestBacktestDefaultIsRealistic:
    """The backtest default is live_parity_streaming: an unspecified-mode
    backtest reproduces what would actually occur in live trading."""

    def test_request_default_enrichment_mode_is_live_parity(self):
        """DTO default flips to live_parity_streaming."""
        req = BacktestStrategyDefinitionRequest(definition="{}", bars=[])
        assert req.enrichment_mode == "live_parity_streaming"

    def test_unspecified_mode_backtest_is_causal(self):
        """Default (no enrichment_mode specified) uses live_parity_streaming."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        request = BacktestStrategyDefinitionRequest(
            definition=_STRATEGY_YAML.read_text(encoding="utf-8"),
            bars=bars,
            informative_bars=info,
            execution=ExecutionConfig(market_calendar="crypto_24_7"),
            symbol="SOL",
            interval="30min",
        )
        result = _make_use_case().execute(request)
        assert result.valid and result.result is not None

        # Default mode is causal + flagged safe
        assert result.result.enrichment_mode == "live_parity_streaming"
        assert result.result.live_parity_safe is True
        assert result.result.trades, "Default backtest produced no trades"
