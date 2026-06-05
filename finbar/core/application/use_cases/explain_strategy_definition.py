"""ExplainStrategyDefinitionUseCase — explain v2 strategy JSON."""

from finbar.core.application.services.description_visitor import DescriptionVisitor
from finbar.core.application.services.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser,
)
from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.interfaces.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser as ParserInterface,
)


class ExplainStrategyDefinitionUseCase:
    """Produce a concise human-readable explanation for a JSON strategy."""

    def __init__(self, parser: ParserInterface | None = None):
        """Create the use case with an injectable parser.

        Args:
            parser: V2 strategy JSON parser (domain interface).
        """
        self._parser = parser or StrategyDefinitionV2Parser()

    def execute(self, definition: str | dict, params: dict | None = None) -> dict:
        """Validate and explain a v2 strategy definition."""
        result = self._parser.parse(definition, params or {})
        if not result.valid or result.definition is None:
            return {
                "valid": False,
                "errors": [_diagnostic_to_dict(error) for error in result.errors],
                "explanation": "Strategy definition is invalid.",
            }

        definition_v2 = result.definition
        lines: list[str] = []

        lines.append(f"# {definition_v2.name}")
        if definition_v2.description:
            lines.append(definition_v2.description)

        _append_parameters(definition_v2, lines)
        _append_indicators(definition_v2, lines)
        _append_features(definition_v2, lines)
        _append_risk(definition_v2, lines)
        _append_sides(definition_v2, lines)

        if result.required_indicators:
            lines.append("")
            lines.append("## Requirements")
            lines.append("Indicators: " + ", ".join(result.required_indicators))

        if result.warnings:
            lines.append("")
            lines.append("## Warnings")
            for warning in result.warnings:
                lines.append(f"- {warning.message}")

        return {
            "valid": True,
            "schema_version": definition_v2.schema_version,
            "name": definition_v2.name,
            "required_indicators": result.required_indicators,
            "explanation": "\n".join(lines),
            "errors": [],
            "warnings": [_diagnostic_to_dict(w) for w in result.warnings],
        }


# ---------------------------------------------------------------------------
# Section helpers — each appends to the lines list
# ---------------------------------------------------------------------------


def _append_parameters(definition: StrategyDefinitionV2, lines: list[str]) -> None:
    if not definition.parameters:
        return
    lines.append("")
    lines.append("## Parameters")
    for name, param in definition.parameters.items():
        bounds = ""
        if param.minimum is not None or param.maximum is not None:
            lo = param.minimum or ""
            hi = param.maximum or ""
            bounds = f" [{lo}..{hi}]"
        lines.append(f"- {name} ({param.type}): {param.default}{bounds}")


def _append_indicators(definition: StrategyDefinitionV2, lines: list[str]) -> None:
    if not definition.indicators:
        return
    lines.append("")
    lines.append("## Indicators")
    for ind in definition.indicators:
        period = f", period={ind.period}" if ind.period else ""
        lines.append(f"- {ind.name} \u2248 {ind.concrete_name} ({ind.type}{period})")


def _append_features(definition: StrategyDefinitionV2, lines: list[str]) -> None:
    if not definition.features:
        return
    lines.append("")
    lines.append("## Features")
    for feat in definition.features:
        detail = f"source={feat.source}"
        if feat.window:
            detail += f", window={feat.window}"
        if feat.shift:
            detail += f", shift={feat.shift}"
        lines.append(f"- {feat.name} ({feat.type}): {detail}")


def _append_risk(definition: StrategyDefinitionV2, lines: list[str]) -> None:
    if definition.risk is None:
        return
    risk = definition.risk
    lines.append("")
    lines.append("## Risk")
    stop_text = _risk_line(risk.stop_loss_type, risk.stop_multiplier, risk.stop_pct)
    lines.append(f"- Stop-loss: {stop_text}")
    target_text = _risk_line(
        risk.take_profit_type, risk.take_profit_multiplier, risk.take_profit_pct
    )
    lines.append(f"- Take-profit: {target_text}")
    if risk.risk_reward_ratio > 0:
        lines.append(f"- Risk/Reward ratio: {risk.risk_reward_ratio}")


def _append_sides(definition: StrategyDefinitionV2, lines: list[str]) -> None:
    lines.append("")
    lines.append("## Sides")
    for side, rules in definition.sides.items():
        lines.append(f"### {side.title()}")
        entry_visitor = DescriptionVisitor()
        entry_visitor.visit_group(rules.entry)
        lines.append(f"Entry: {entry_visitor.result}")
        if rules.exit is not None:
            exit_visitor = DescriptionVisitor()
            exit_visitor.visit_group(rules.exit)
            lines.append(f"Exit: {exit_visitor.result}")
        else:
            lines.append("Exit: (none \u2014 position held indefinitely)")


def _risk_line(risk_type: str, multiplier: float, pct: float) -> str:
    if risk_type == "atr":
        return f"ATR x{multiplier}"
    if risk_type == "fixed_pct":
        return f"{pct * 100:.1f}%"
    if risk_type == "risk_reward":
        return "risk/reward"
    return risk_type


def _diagnostic_to_dict(error) -> dict:
    return {"path": error.path, "message": error.message, "code": error.code}
