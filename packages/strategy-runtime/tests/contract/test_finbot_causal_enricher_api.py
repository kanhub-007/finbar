"""Finbot-ready package causal enricher API contract.

Scenario 14: Finbot can create the package enricher from a parsed strategy
and feed closed candles by timeframe alias without importing Finbar app code.
"""

from __future__ import annotations

from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
)
from finbar_strategy_runtime.indicators import (
    causal_multi_timeframe_streaming_enricher as causal_mtf,
)
from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)


def _strategy_definition() -> dict:
    """Return a simple primary + informative strategy definition."""
    return {
        "schema_version": "2.0",
        "name": "finbot_ready_vwap_sma",
        "timeframes": {
            "primary": "30min",
            "informative": [{"alias": "h1", "interval": "1h"}],
        },
        "indicators": [
            {"name": "primary_vwap", "type": "vwap"},
            {
                "name": "h1_sma_fast",
                "type": "sma",
                "period": 3,
                "timeframe": "h1",
            },
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [
                            {
                                "left": "close",
                                "operator": ">",
                                "right": "primary_vwap",
                            }
                        ]
                    }
                }
            }
        },
    }


def _bar(ts: str, close: float) -> dict:
    """Return one deterministic closed candle."""
    return {
        "timestamp": ts,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1000.0,
    }


class TestFinbotCausalEnricherApi:
    """Black-box tests for the Finbot-facing package API."""

    def test_from_strategy_definition_and_update_alias_contract(self):
        """Closed candle updates return flat enriched primary rows when ready."""
        validation = StrategyDefinitionParser().parse(_strategy_definition())
        assert validation.valid is True
        assert validation.definition is not None
        factory = causal_mtf.CausalMultiTimeframeStreamingEnricher
        enricher = factory.from_strategy_definition(
            validation.definition,
            validation.primary_required_indicators,
            validation.informative_required_indicators,
        )

        latest = None
        for hour in range(12):
            info_result = enricher.update(
                "h1",
                _bar(f"2026-03-01T{hour:02d}:00:00Z", 100.0 + hour),
            )
            assert info_result is None
            latest = enricher.update(
                "primary",
                _bar(f"2026-03-01T{hour:02d}:30:00Z", 101.0 + hour),
            )

        assert latest is not None
        assert latest.is_ready is True
        assert latest.values["close"] == 112.0
        assert "vwap" in latest.values
        assert "sma_3_1h" in latest.values
        assert all(not hasattr(value, "iloc") for value in latest.values.values())

        signal = JsonRuleBasedStrategy(validation.definition).on_bar(
            latest.values,
            position=None,
        )
        assert signal is not None

    def test_informative_updates_do_not_emit_primary_decision_row(self):
        """Only a primary candle close emits a row for strategy evaluation."""
        validation = StrategyDefinitionParser().parse(_strategy_definition())
        assert validation.definition is not None
        factory = causal_mtf.CausalMultiTimeframeStreamingEnricher
        enricher = factory.from_strategy_definition(
            validation.definition,
            validation.primary_required_indicators,
            validation.informative_required_indicators,
        )

        assert enricher.update("h1", _bar("2026-03-01T00:00:00Z", 100.0)) is None
        assert enricher.latest() is None
