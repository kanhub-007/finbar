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
        lines = [
            f"Strategy '{definition_v2.name}': {definition_v2.description}".strip()
        ]
        for side, rules in definition_v2.sides.items():
            lines.append(f"{side.title()} entry: {_describe_group(rules.entry)}")
            if rules.exit is not None:
                lines.append(f"{side.title()} exit: {_describe_group(rules.exit)}")
        if result.required_indicators:
            lines.append(
                "Requires indicators: " + ", ".join(result.required_indicators)
            )
        return {
            "valid": True,
            "schema_version": definition_v2.schema_version,
            "name": definition_v2.name,
            "required_indicators": result.required_indicators,
            "explanation": "\n".join(lines),
            "errors": [],
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


def _diagnostic_to_dict(error) -> dict:
    return {"path": error.path, "message": error.message, "code": error.code}
