"""Contract tests for parser rejection of unknown metric names — Scenario 1.4.

Verifies the parser rejects unknown metric names referenced in conditions
with an ``unknown_operand`` error code.
"""

from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)


class TestUnknownMetricRejection:
    """The parser must reject unknown metric names in condition operands."""

    def test_unknown_operand_in_condition_rejected(self):
        """A strategy referencing 'nonexistent_metric' in a condition must
        fail validation with an unknown_operand error."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "bad_operand",
            "timeframes": {"primary": "1d"},
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "operator": ">",
                                    "left": "nonexistent_metric",
                                    "right": 100,
                                }
                            ]
                        }
                    },
                    "exit": {
                        "condition": {
                            "operator": "is_true",
                            "left": "nonexistent_metric",
                        }
                    },
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        assert any(e.code == "unknown_operand" for e in result.errors)

    def test_known_metric_accepted(self):
        """A strategy referencing a known metric (vwap) must parse validly."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "good_operand",
            "timeframes": {"primary": "1d"},
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "operator": ">",
                            "left": "close",
                            "right": 100,
                        }
                    },
                    "exit": {
                        "condition": {
                            "operator": "<",
                            "left": "close",
                            "right": 200,
                        }
                    },
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is True
        assert not any(e.code == "unknown_operand" for e in result.errors)

    def test_unknown_operand_error_has_path(self):
        """The unknown_operand error must include a JSONPath-like path."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "bad_path",
            "timeframes": {"primary": "1d"},
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "operator": ">",
                                    "left": "ghost_metric",
                                    "right": 50,
                                }
                            ]
                        }
                    },
                    "exit": {
                        "condition": {
                            "operator": "is_true",
                            "left": "ghost_metric",
                        }
                    },
                }
            },
        }

        result = parser.parse(raw)

        assert result.valid is False
        operand_errors = [e for e in result.errors if e.code == "unknown_operand"]
        assert len(operand_errors) > 0
        assert all(e.path for e in operand_errors)
