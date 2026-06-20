"""Finbar Strategy Runtime — parser, evaluator, indicator calculator.

This package contains the strategy definition parser, condition evaluator,
risk calculator, indicator calculator, and domain entities shared between
Finbar (authoring/backtesting) and Finbot (live trading).

Subpackages:
    domain/      — Pure entities, interfaces, math services (VP, AMT, auction state, proxies)
    parser/      — YAML/JSON strategy definition parser and validators
    evaluation/  — Condition evaluator, rule-based strategy runtime, risk calculator
    indicators/  — Pandas-backed indicator/enrichment calculation (requires [pandas] extra)

Usage:
    from finbar_strategy_runtime.parser import StrategyDefinitionParser

    parser = StrategyDefinitionParser()
    result = parser.parse(yaml_text)
    if result.valid:
        print(result.definition.name)
"""

__version__ = "0.3.0"
