"""Validation test for the auction drive JSON strategy."""

import json
from pathlib import Path

from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)


def test_auction_drive_json_parses():
    """The auction drive JSON fixture parses with all SDK features."""
    text = Path("tests/fixtures/strategies/auction_drive_json.json").read_text()
    strategy = json.loads(text)

    result = StrategyDefinitionParser().parse(strategy)

    assert result.valid is True, f"Validation errors: {result.errors}"
    assert result.definition is not None

    # Multi-timeframe
    assert result.definition.timeframes is not None
    assert result.definition.timeframes.primary == "1h"
    assert result.definition.timeframes.informative[0].alias == "daily"

    # Split enrichment instructions
    assert result.informative_required_indicators == {"daily": ["sma_50", "sma_200"]}

    # Parameters resolve
    assert result.definition.resolved_params["trend_fast"] == 50
    assert result.definition.resolved_params["stop_atr_mult"] == 2.5

    # Risk
    assert result.definition.risk is not None
    assert result.definition.risk.stop_loss_type == "atr"

    # Indicators present (6 declared)
    assert len(result.definition.indicators) == 6

    # Features present (3 declared: body_pct + 2 formulas)
    assert len(result.definition.features) == 3


def test_auction_drive_json_explains():
    """The auction drive JSON strategy produces a readable explanation."""
    text = Path("tests/fixtures/strategies/auction_drive_json.json").read_text()
    from finbar.core.application.use_cases.explain_strategy_definition import (
        ExplainStrategyDefinitionUseCase,
    )

    result = ExplainStrategyDefinitionUseCase().execute(text)

    assert result.get("valid") is True
    explanation = result.get("explanation", "")
    assert "trend" in explanation.lower()
    assert "vwap" in explanation.lower()
