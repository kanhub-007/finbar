"""ExplainStrategyDefinitionUseCase — explain v2 strategy JSON."""

from finbar.core.application.services.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser,
)
from finbar.core.domain.entities.condition_group import ConditionGroup


class ExplainStrategyDefinitionUseCase:
    """Produce a concise human-readable explanation for a JSON strategy."""

    def __init__(self, parser: StrategyDefinitionV2Parser | None = None):
        """Create the use case with an injectable parser."""
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

        if definition_v2.parameters:
            lines.append("")
            lines.append("## Parameters")
            for name, param in definition_v2.parameters.items():
                bounds = ""
                if param.minimum is not None or param.maximum is not None:
                    lo = param.minimum or ""
                    hi = param.maximum or ""
                    bounds = f" [{lo}..{hi}]"
                lines.append(f"- {name} ({param.type}): {param.default}{bounds}")

        if definition_v2.indicators:
            lines.append("")
            lines.append("## Indicators")
            for ind in definition_v2.indicators:
                lines.append(
                    f"- {ind.name} ≈ {ind.concrete_name} ({ind.type}{_period_str(ind)})"
                )

        if definition_v2.features:
            lines.append("")
            lines.append("## Features")
            for feat in definition_v2.features:
                detail = f"source={feat.source}"
                if feat.window:
                    detail += f", window={feat.window}"
                if feat.shift:
                    detail += f", shift={feat.shift}"
                lines.append(f"- {feat.name} ({feat.type}): {detail}")

        if definition_v2.risk:
            lines.append("")
            lines.append("## Risk")
            stop_text = _risk_line(
                definition_v2.risk.stop_loss_type,
                definition_v2.risk.stop_multiplier,
                definition_v2.risk.stop_pct,
            )
            lines.append(f"- Stop-loss: {stop_text}")
            target_text = _risk_line(
                definition_v2.risk.take_profit_type,
                definition_v2.risk.take_profit_multiplier,
                definition_v2.risk.take_profit_pct,
            )
            lines.append(f"- Take-profit: {target_text}")
            if definition_v2.risk.risk_reward_ratio > 0:
                lines.append(
                    f"- Risk/Reward ratio: {definition_v2.risk.risk_reward_ratio}"
                )

        lines.append("")
        lines.append("## Sides")
        for side, rules in definition_v2.sides.items():
            lines.append(f"### {side.title()}")
            lines.append(f"Entry: {_describe_group(rules.entry)}")
            if rules.exit is not None:
                lines.append(f"Exit: {_describe_group(rules.exit)}")
            else:
                lines.append("Exit: (none — position held indefinitely)")

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


def _describe_group(group: ConditionGroup) -> str:
    if group.kind == "condition" and group.condition is not None:
        condition = group.condition
        left = condition.left.label or str(condition.left.value)
        if condition.right is None:
            return f"{left} {condition.operator}"
        right = condition.right.label or str(condition.right.value)
        return f"{left} {condition.operator} {right}"
    if group.kind == "not" and group.children:
        return "NOT (" + _describe_group(group.children[0]) + ")"
    joiner = " AND " if group.kind == "all" else " OR "
    return "(" + joiner.join(_describe_group(child) for child in group.children) + ")"


def _period_str(indicator) -> str:
    if indicator.period:
        return f", period={indicator.period}"
    return ""


def _risk_line(risk_type: str, multiplier: float, pct: float) -> str:
    if risk_type == "atr":
        return f"ATR x{multiplier}"
    if risk_type == "fixed_pct":
        return f"{pct*100:.1f}%"
    if risk_type == "risk_reward":
        return "risk/reward"
    return risk_type


def _diagnostic_to_dict(error) -> dict:
    return {"path": error.path, "message": error.message, "code": error.code}
