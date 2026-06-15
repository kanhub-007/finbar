"""End-to-end tests — VSA/SMC/regime strategies validate through the parser.

Spec 2026-06-15, Slice 2 ("End-to-end — a VSA strategy validates"). Proves
that theory-family strategies (VSA, SMC, Bill Williams, regime) that
reference catalogued+handled metrics are now functional end-to-end, not
merely declarable — the real parser accepts them and resolves the correct
concrete column names.

Classical school: real parser + real catalog, outcome-based assertions.
"""

import pytest

from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar_strategy_runtime.parser.unified_metric_catalog import (
    UnifiedMetricCatalog,
)


@pytest.fixture
def parser() -> StrategyDefinitionParser:
    """Build a parser backed by the real UnifiedMetricCatalog."""
    return StrategyDefinitionParser(catalog=UnifiedMetricCatalog())


def _strategy(indicator_decls: list[str], entry_left: str, exit_left: str) -> str:
    """Build a minimal valid strategy YAML referencing the given indicators.

    Each entry in ``indicator_decls`` becomes both an indicator declaration
    (name == type == the metric) and is referenced in entry/exit conditions.
    """
    indicators_yaml = "\n".join(
        f"  - {{name: {c}, type: {c}, timeframe: primary}}" for c in indicator_decls
    )
    return f"""
schema_version: "2.0"
name: e2e_smoke
timeframes: {{primary: 1h}}
indicators:
{indicators_yaml}
sides:
  long:
    entry:
      condition: {{all: [{{operator: is_true, left: {entry_left}}}]}}
    exit:
      condition: {{any: [{{operator: is_true, left: {exit_left}}}]}}
risk:
  stop_loss: {{type: atr, multiplier: 3.5}}
  take_profit: {{type: risk_reward, ratio: 1.5}}
"""


class TestVsaStrategyValidates:
    """A strategy referencing VSA metrics must validate, with correct
    concrete column names resolved."""

    def test_vsa_strategy_validates(self, parser):
        definition = _strategy(
            ["atr", "bag_holding", "effort_result_divergence"],
            entry_left="bag_holding",
            exit_left="effort_result_divergence",
        )
        result = parser.parse(definition)

        assert result.valid, f"Validation failed: {result.errors}"
        assert result.errors == []

        concrete = {ind.concrete_name for ind in result.definition.indicators}
        assert "bag_holding" in concrete
        assert "effort_result_divergence" in concrete

    def test_vsa_required_indicators_carry_concrete_names(self, parser):
        """required_indicators lists the concrete columns the engine must compute."""
        definition = _strategy(
            ["atr", "bag_holding", "effort_result_divergence"],
            entry_left="bag_holding",
            exit_left="effort_result_divergence",
        )
        result = parser.parse(definition)

        assert result.valid, result.errors
        assert "bag_holding" in result.required_indicators
        assert "effort_result_divergence" in result.required_indicators


class TestRegimeAndSmcStrategiesValidate:
    """Regime classifiers and SMC metrics validate end-to-end."""

    def test_market_regime_strategy_validates(self, parser):
        definition = _strategy(
            ["market_regime"], entry_left="market_regime", exit_left="close"
        )
        result = parser.parse(definition)
        assert result.valid, result.errors
        assert "market_regime" in {
            ind.concrete_name for ind in result.definition.indicators
        }

    def test_smc_metrics_strategy_validates(self, parser):
        """bos / choch / bullish_fvg (SMC/ICT) validate end-to-end."""
        definition = _strategy(
            ["bos", "choch", "bullish_fvg"], entry_left="bos", exit_left="choch"
        )
        result = parser.parse(definition)
        assert result.valid, result.errors
        concrete = {ind.concrete_name for ind in result.definition.indicators}
        assert {"bos", "choch", "bullish_fvg"} <= concrete


class TestUnhandledCataloguedMetricStillRejected:
    """Negative: a catalogued-but-unhandled metric (vix) still fails validation."""

    def test_vix_strategy_rejected_with_unsupported_indicator(self, parser):
        definition = _strategy(["vix"], entry_left="vix", exit_left="close")
        result = parser.parse(definition)

        assert result.valid is False
        codes = {e.code for e in result.errors}
        assert "unsupported_indicator" in codes, (
            f"Expected unsupported_indicator for catalogued-unhandled 'vix', "
            f"got codes: {codes}"
        )
