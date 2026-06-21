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
_DB_PATH = _REPO_ROOT / "data" / "finbar.db"
_STRATEGY_YAML = (
    _REPO_ROOT
    / "strategies"
    / "intraday_scalper"
    / "14_amt_value_reject_30m_1h_mtf.yaml"
)

needs_finbar_data = pytest.mark.skipif(
    not _DB_PATH.exists() or not _STRATEGY_YAML.exists(),
    reason="Finbar monorepo data not found",
)


def _load_bars(interval: str, limit: int) -> list[dict]:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT timestamp, open, high, low, close, volume "
        "FROM price_bar WHERE symbol = 'SOL' AND interval = ? "
        "ORDER BY timestamp ASC",
        (interval,),
    ).fetchall()[-limit:]
    conn.close()
    return [dict(r) for r in rows]


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
        execution=ExecutionConfig(),
        symbol="SOL",
        interval="30min",
        enrichment_mode=mode,
    )


@needs_finbar_data
class TestBacktestLiveParityMode:
    """Black-box: live_parity_streaming mode produces causal results."""

    def test_live_parity_first_trade_precedes_batch(self):
        """Live-parity first trade entry is earlier than batch (row 17 vs 95)."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        use_case = _make_use_case()

        live = use_case.execute(_request(bars, info, "live_parity_streaming"))
        batch = use_case.execute(_request(bars, info, "batch_full_frame"))

        assert live.valid and live.result is not None
        assert batch.valid and batch.result is not None

        live_trades = live.result.trades
        batch_trades = batch.result.trades
        assert live_trades, "Live-parity mode produced no trades"
        assert batch_trades, "Batch mode produced no trades"

        assert live_trades[0]["entry_date"] < batch_trades[0]["entry_date"], (
            f"Live first trade {live_trades[0]['entry_date']} should precede "
            f"batch first trade {batch_trades[0]['entry_date']}"
        )

    def test_live_parity_first_trade_at_row_17_timestamp(self):
        """Live-parity first trade entry matches the streaming reference (row 17)."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        use_case = _make_use_case()

        live = use_case.execute(_request(bars, info, "live_parity_streaming"))
        assert live.valid and live.result is not None

        first_entry = live.result.trades[0]["entry_date"]
        # Row 17 of the last-500 30min bars is bars[17].timestamp
        expected_ts = bars[17]["timestamp"]
        assert str(first_entry).startswith(
            str(expected_ts)[:10]
        ), f"Live first trade {first_entry} should match row 17 ({expected_ts})"

    def test_batch_mode_first_trade_at_row_95(self):
        """Batch mode first trade documents the defect (row 95)."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        use_case = _make_use_case()

        batch = use_case.execute(_request(bars, info, "batch_full_frame"))
        assert batch.valid and batch.result is not None

        first_entry = batch.result.trades[0]["entry_date"]
        expected_ts = bars[95]["timestamp"]
        assert str(first_entry).startswith(
            str(expected_ts)[:10]
        ), f"Batch first trade {first_entry} should match row 95 ({expected_ts})"


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

    def test_unspecified_mode_backtest_is_causal_row_17(self):
        """A backtest that does NOT pass enrichment_mode fires at row 17
        (causal), not row 95 (lookahead) — i.e. it matches live trading."""
        bars = _load_bars("30min", 500)
        info = {"h1": _load_bars("1h", 600)}
        request = BacktestStrategyDefinitionRequest(
            definition=_STRATEGY_YAML.read_text(encoding="utf-8"),
            bars=bars,
            informative_bars=info,
            execution=ExecutionConfig(),
            symbol="SOL",
            interval="30min",
        )
        result = _make_use_case().execute(request)
        assert result.valid and result.result is not None

        # Default mode is causal + flagged safe
        assert result.result.enrichment_mode == "live_parity_streaming"
        assert result.result.live_parity_safe is True

        # First trade matches the live/causal reference (row 17), NOT batch (95)
        first_entry = result.result.trades[0]["entry_date"]
        expected_ts = bars[17]["timestamp"]
        assert str(first_entry).startswith(
            str(expected_ts)[:10]
        ), f"Default backtest {first_entry} should be causal row 17, not batch row 95"
