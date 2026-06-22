"""Contract test for causal enrichment artifacts."""

from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (
    CausalMultiTimeframeStreamingEnricher,
)
from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)


def _bars(count=80):
    return [
        {
            "timestamp": f"2026-03-{(i // 24) + 1:02d}T{i % 24:02d}:00:00Z",
            "open": 100.0 + i, "high": 101.0 + i,
            "low": 99.0 + i, "close": 100.5 + i, "volume": 1000.0 + i * 10,
        }
        for i in range(count)
    ]


def _h1_bars(count=40):
    return [
        {
            "timestamp": f"2026-03-{(i // 12) + 1:02d}T{(i % 12) * 2:02d}:00:00Z",
            "open": 100.0 + i * 2, "high": 101.0 + i * 2,
            "low": 99.0 + i * 2, "close": 100.5 + i * 2, "volume": 2000.0 + i * 20,
        }
        for i in range(count)
    ]


def _mtf_strategy():
    return {
        "schema_version": "2.0",
        "name": "causal_artifact_test",
        "timeframes": {
            "primary": "1h",
            "informative": [{"alias": "h1", "interval": "1h"}],
        },
        "indicators": [
            {"name": "primary_vwap", "type": "vwap", "timeframe": "primary"},
            {"name": "h1_sma", "type": "sma", "period": 3, "timeframe": "h1"},
        ],
        "sides": {
            "long": {
                "entry": {
                    "condition": {
                        "all": [{"left": "close", "operator": ">", "right": "primary_vwap"}],
                    }
                }
            }
        },
    }


class TestCausalEnrichBars:
    """Black-box: package-level causal_enrich_bars produces correct rows."""

    def test_causal_enrich_bars_produces_correct_columns(self):
        validation = StrategyDefinitionParser().parse(_mtf_strategy())
        assert validation.valid and validation.definition is not None

        frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
            primary_bars=_bars(80),
            informative_bars={"h1": _h1_bars(40)},
            definition=validation.definition,
            primary_indicators=validation.primary_required_indicators,
            informative_indicators=validation.informative_required_indicators,
        )

        assert len(frame) == 80
        assert "close" in frame.columns
        assert "vwap" in frame.columns
        assert "sma_3_1h" in frame.columns
        assert not any(frame[col].isna().all() for col in ("close", "vwap"))
        assert not frame["vwap"].iloc[-1:].isna().all()

    def test_causal_enrich_bars_single_timeframe(self):
        single = dict(_mtf_strategy())
        single["timeframes"] = {"primary": "1h", "informative": []}
        single["indicators"] = [
            {"name": "primary_vwap", "type": "vwap", "timeframe": "primary"},
        ]
        validation = StrategyDefinitionParser().parse(single)
        assert validation.valid and validation.definition is not None

        frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
            primary_bars=_bars(50),
            informative_bars={},
            definition=validation.definition,
            primary_indicators=validation.primary_required_indicators,
            informative_indicators={},
        )

        assert len(frame) == 50
        assert "vwap" in frame.columns
        assert not any(c.endswith("_1h") for c in frame.columns)
