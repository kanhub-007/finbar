"""Validation test for the auction drive JSON strategy."""

import json
from pathlib import Path

from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)


def test_auction_drive_json_parses():
    text = Path("tests/fixtures/strategies/auction_drive_json.json").read_text()
    strategy = json.loads(text)

    result = StrategyDefinitionParser().parse(strategy)

    assert result.valid is True, f"Errors: {result.errors}"
    assert result.definition is not None
    assert result.definition.timeframes is not None
    assert result.definition.timeframes.primary == "1h"
    assert len(result.definition.indicators) == 6
    assert len(result.definition.features) == 3
    assert result.definition.risk is not None
    assert result.required_columns


def test_auction_drive_json_explains():
    text = Path("tests/fixtures/strategies/auction_drive_json.json").read_text()
    from finbar.core.application.use_cases.explain_strategy_definition import (
        ExplainStrategyDefinitionUseCase,
    )

    result = ExplainStrategyDefinitionUseCase().execute(text)

    assert result.get("valid") is True
    explanation = result.get("explanation", "")
    assert "trend" in explanation.lower()
    assert "vwap" in explanation.lower()
