"""Integration test proving the parser accepts new metrics — C1 regression.

This test goes through the REAL parser (not the catalog directly) to
verify that a strategy YAML referencing a new metric (e.g.
``corwin_schultz_spread``) is accepted, not rejected with
``unknown_operand``.
"""

from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)


class TestParserAcceptsNewMetrics:
    """The parser must accept all new metric names in conditions."""

    def test_corwin_schultz_spread_accepted(self):
        """A strategy referencing corwin_schultz_spread must parse validly."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "test_spread_strategy",
            "timeframes": {"primary": "1d"},
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "operator": ">",
                            "left": "corwin_schultz_spread",
                            "right": 0.01,
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
        assert result.valid is True, (
            f"Parser rejected corwin_schultz_spread: "
            f"{[e.message for e in result.errors]}"
        )

    def test_fib_618_retrace_accepted(self):
        """A strategy referencing fib_618_retrace must parse validly."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "test_fib_strategy",
            "timeframes": {"primary": "1d"},
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "operator": ">",
                            "left": "fib_618_retrace",
                            "right": 0.5,
                        }
                    },
                    "exit": {
                        "condition": {
                            "operator": "is_true",
                            "left": "close",
                        }
                    },
                }
            },
        }
        result = parser.parse(raw)
        assert result.valid is True

    def test_funding_rate_accepted(self):
        """A strategy referencing funding_rate must parse validly."""
        parser = StrategyDefinitionParser()
        raw = {
            "schema_version": "2.0",
            "name": "test_funding_strategy",
            "timeframes": {"primary": "1d"},
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "operator": ">",
                            "left": "funding_rate",
                            "right": 0.0001,
                        }
                    },
                    "exit": {
                        "condition": {
                            "operator": "<",
                            "left": "funding_rate",
                            "right": 0,
                        }
                    },
                }
            },
        }
        result = parser.parse(raw)
        assert result.valid is True
