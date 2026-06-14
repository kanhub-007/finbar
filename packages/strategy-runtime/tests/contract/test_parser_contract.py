"""Contract tests for the strategy runtime package — parsing and validation.

These are black-box, Classical-school tests: real runtime objects, assertions
on outcomes. No mocks, no interaction assertions, no private method verification.
"""

import json
import os
from pathlib import Path

import pytest

from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def _load_yaml_fixture(name: str) -> str:
    """Load a strategy YAML fixture from the finbar strategies directory."""
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_text()


# ---------------------------------------------------------------------------
# Scenario 1: Runtime package exposes canonical strategy parsing and validation
# ---------------------------------------------------------------------------


class TestStrategyParsing:
    """Black-box contract tests for strategy parsing and validation."""

    def test_parse_valid_amt_dip_buyer_strategy(self):
        """Parse a valid AMT dip buyer YAML strategy — should produce a valid
        StrategyDefinition with correct fields."""
        parser = StrategyDefinitionParser()
        yaml_text = _load_yaml_fixture("amt_dip_buyer_final.yaml")

        result = parser.parse(yaml_text)

        assert result.valid is True
        assert result.definition is not None
        assert result.definition.name == "amt_dip_buyer_final"
        assert result.definition.schema_version == "2.0"
        assert result.definition.description.startswith("AMT Rule 1 dip buyer")
        assert "long" in result.definition.sides
        assert result.definition.sides["long"].entry is not None
        assert result.definition.sides["long"].exit is not None
        # Ensure no errors
        assert len(result.errors) == 0

    def test_parse_amt_v2_strategy(self):
        """Parse the AMT v2 vol filter strategy — should be valid."""
        parser = StrategyDefinitionParser()
        yaml_text = _load_yaml_fixture("amt_v2_vol_filter.yaml")

        result = parser.parse(yaml_text)

        assert result.valid is True
        assert result.definition is not None
        assert result.definition.name == "amt_v2_vol_filter"
        assert result.definition.schema_version == "2.0"

    def test_parse_json_strategy(self):
        """Parse a strategy provided as a JSON string, not YAML."""
        parser = StrategyDefinitionParser()
        json_text = json.dumps(
            {
                "schema_version": "2.0",
                "name": "sma_cross_json",
                "description": "Simple SMA crossover",
                "indicators": [
                    {"name": "sma_fast", "type": "sma", "period": 10},
                    {"name": "sma_slow", "type": "sma", "period": 30},
                ],
                "sides": {
                    "long": {
                        "entry": {
                            "condition": {
                                "operator": "crosses_above",
                                "left": "sma_fast",
                                "right": "sma_slow",
                            }
                        },
                        "exit": {
                            "condition": {
                                "operator": "crosses_below",
                                "left": "sma_fast",
                                "right": "sma_slow",
                            }
                        },
                    }
                },
            }
        )

        result = parser.parse(json_text)

        assert result.valid is True
        assert result.definition is not None
        assert result.definition.name == "sma_cross_json"
        assert len(result.definition.indicators) == 2


class TestStrategyValidationErrors:
    """Black-box tests for validation failures."""

    def test_unknown_indicator_produces_error_with_path(self):
        """Unknown indicator type should produce an invalid result with a
        path-specific error pointing to the indicator name."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "bad_indicator",
            "indicators": [{"name": "made_up", "type": "nonexistent_indicator_xyz"}],
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "made_up"}},
                    "exit": {"condition": {"operator": "is_true", "left": "made_up"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        assert result.definition is None
        assert len(result.errors) > 0
        # At least one error should mention the indicator name
        error_messages = " ".join(e.message for e in result.errors)
        assert "made_up" in error_messages or "nonexistent" in error_messages.lower()

    def test_unsupported_operator_produces_error(self):
        """An unsupported comparison operator should result in an invalid parse."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "bad_operator",
            "indicators": [
                {"name": "my_rsi", "type": "rsi", "period": 14},
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "operator": "__invalid_operator_xyz__",
                            "left": "my_rsi",
                            "right": 50,
                        }
                    },
                    "exit": {"condition": {"operator": "is_true", "left": "my_rsi"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        assert len(result.errors) > 0

    def test_parameter_override_outside_min_max_produces_error(self):
        """A parameter override outside the declared min/max range should fail."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "param_test",
            "parameters": {
                "lookback": {
                    "type": "int",
                    "default": 20,
                    "minimum": 5,
                    "maximum": 50,
                }
            },
            "indicators": [
                {"name": "ma", "type": "sma", "period": "{{ lookback }}"},
            ],
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "ma"}},
                    "exit": {"condition": {"operator": "is_true", "left": "ma"}},
                }
            },
        }

        result = parser.parse(raw, param_overrides={"lookback": 100})

        assert result.valid is False
        assert len(result.errors) > 0

    def test_schema_version_other_than_2_0_is_invalid(self):
        """Only schema_version '2.0' is currently supported."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "1.0",
            "name": "old_schema",
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "close"}},
                    "exit": {"condition": {"operator": "is_true", "left": "close"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        error_messages = " ".join(e.message for e in result.errors)
        assert "schema_version" in error_messages.lower()

    def test_empty_name_produces_error(self):
        """A strategy with an empty name should be invalid."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "",
            "sides": {
                "long": {
                    "entry": {"condition": {"operator": "is_true", "left": "close"}},
                    "exit": {"condition": {"operator": "is_true", "left": "close"}},
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        error_messages = " ".join(e.message for e in result.errors)
        assert "name" in error_messages.lower()



class TestArchitecture:
    """Architecture tests — the package must not depend on Finbar app layers."""

    FORBIDDEN_IMPORTS = [
        "finbar.presentation",
        "finbar.startup",
        "finbar.infrastructure.repositories",
        "finbar.infrastructure.data",
        "finbar.infrastructure.tables",
        "fastapi",
        "fastmcp",
        "sqlalchemy",
        "yfinance",
        "hyperliquid",
    ]

    def test_package_has_no_forbidden_imports(self):
        """The runtime package must not import Finbar presentation, startup,
        repositories, fetchers, or ORM frameworks."""
        import ast
        import importlib

        package_root = Path(__file__).resolve().parents[2] / "finbar_strategy_runtime"
        violating = []

        for py_file in package_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imp = alias.name
                        for forbidden in self.FORBIDDEN_IMPORTS:
                            if imp == forbidden or imp.startswith(forbidden + "."):
                                violating.append(f"{py_file.name}: imports {imp}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for forbidden in self.FORBIDDEN_IMPORTS:
                        if module == forbidden or module.startswith(forbidden + "."):
                            violating.append(f"{py_file.name}: from {module}")

        assert len(violating) == 0, (
            f"Forbidden imports found:\n" + "\n".join(violating)
        )
