"""StrategyConditionParser — parse v2 side rule condition trees."""

from typing import Any

from finbar.core.application.services.strategy_definition_parse_helpers import (
    BINARY_OPERATORS,
    OHLCV_FIELDS,
    UNARY_OPERATORS,
    extract_condition,
    make_error,
    resolve_expression,
)
from finbar.core.application.services.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar.core.domain.entities.condition import Condition
from finbar.core.domain.entities.condition_group import ConditionGroup
from finbar.core.domain.entities.indicator_spec import IndicatorSpec
from finbar.core.domain.entities.operand import Operand
from finbar.core.domain.entities.side_rules import SideRules
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)


class StrategyConditionParser:
    """Parse side-specific entry/exit condition trees."""

    def __init__(self, catalog: IndicatorCapabilityProvider | None = None):
        """Create a condition parser backed by indicator capabilities."""
        self._catalog = catalog or StrategyIndicatorCatalog()

    def parse_sides(
        self,
        raw: Any,
        indicators: list[IndicatorSpec],
        resolved_params: dict[str, Any],
        errors: list[StrategyValidationError],
    ) -> dict[str, SideRules]:
        """Parse the sides object from a v2 strategy definition."""
        if not isinstance(raw, dict) or not raw:
            errors.append(
                make_error("$.sides", "sides must define at least one of long or short")
            )
            return {}
        sides: dict[str, SideRules] = {}
        aliases = {item.name: item.concrete_name for item in indicators}
        for side, spec in raw.items():
            self._parse_side(side, spec, aliases, resolved_params, sides, errors)
        return sides

    def _parse_side(
        self,
        side: str,
        spec: Any,
        aliases: dict[str, str],
        resolved_params: dict[str, Any],
        sides: dict[str, SideRules],
        errors: list[StrategyValidationError],
    ) -> None:
        path = f"$.sides.{side}"
        if side not in ("long", "short"):
            errors.append(make_error(path, "side must be long or short"))
            return
        if not isinstance(spec, dict):
            errors.append(make_error(path, "side spec must be an object"))
            return
        entry_raw = extract_condition(spec.get("entry"))
        if entry_raw is None:
            errors.append(
                make_error(f"{path}.entry.condition", "entry condition is required")
            )
            return
        entry = self._parse_group(
            entry_raw, aliases, resolved_params, f"{path}.entry.condition", errors
        )
        exit_raw = extract_condition(spec.get("exit"))
        exit_group = None
        if exit_raw is not None:
            exit_group = self._parse_group(
                exit_raw, aliases, resolved_params, f"{path}.exit.condition", errors
            )
        sides[side] = SideRules(side=side, entry=entry, exit=exit_group)

    def _parse_group(
        self,
        raw: Any,
        aliases: dict[str, str],
        resolved_params: dict[str, Any],
        path: str,
        errors: list[StrategyValidationError],
    ) -> ConditionGroup:
        if not isinstance(raw, dict):
            errors.append(make_error(path, "condition must be an object"))
            return ConditionGroup(kind="all")
        for kind in ("all", "any"):
            if kind in raw:
                return self._parse_children(
                    kind, raw[kind], aliases, resolved_params, path, errors
                )
        if "not" in raw:
            child = self._parse_group(
                raw["not"], aliases, resolved_params, f"{path}.not", errors
            )
            return ConditionGroup(kind="not", children=[child])
        return ConditionGroup(
            kind="condition",
            condition=self._parse_condition(
                raw, aliases, resolved_params, path, errors
            ),
        )

    def _parse_children(
        self,
        kind: str,
        raw_children: Any,
        aliases: dict[str, str],
        resolved_params: dict[str, Any],
        path: str,
        errors: list[StrategyValidationError],
    ) -> ConditionGroup:
        if not isinstance(raw_children, list) or not raw_children:
            errors.append(
                make_error(f"{path}.{kind}", f"{kind} must be a non-empty array")
            )
            return ConditionGroup(kind=kind)
        children = [
            self._parse_group(
                child, aliases, resolved_params, f"{path}.{kind}[{idx}]", errors
            )
            for idx, child in enumerate(raw_children)
        ]
        return ConditionGroup(kind=kind, children=children)

    def _parse_condition(
        self,
        raw: dict,
        aliases: dict[str, str],
        resolved_params: dict[str, Any],
        path: str,
        errors: list[StrategyValidationError],
    ) -> Condition:
        operator = str(raw.get("operator", "")).strip()
        if operator not in BINARY_OPERATORS | UNARY_OPERATORS:
            errors.append(
                make_error(f"{path}.operator", f"unsupported operator '{operator}'")
            )
        left = self._parse_operand(
            raw.get("left"), aliases, resolved_params, f"{path}.left", errors
        )
        right = None
        if operator in BINARY_OPERATORS:
            right = self._parse_operand(
                raw.get("right"), aliases, resolved_params, f"{path}.right", errors
            )
        return Condition(left=left, operator=operator, right=right)

    def _parse_operand(
        self,
        raw: Any,
        aliases: dict[str, str],
        resolved_params: dict[str, Any],
        path: str,
        errors: list[StrategyValidationError],
    ) -> Operand:
        value = resolve_expression(raw, resolved_params, path, errors)
        if isinstance(value, (int, float, bool, list)):
            return Operand(kind="literal", value=value, label=str(raw))
        if isinstance(value, str):
            return _parse_named_operand(value, aliases, self._catalog, path, errors)
        errors.append(make_error(path, "operand is required"))
        return Operand(kind="literal", value=0, label=str(raw))


def _parse_named_operand(
    value: str,
    aliases: dict[str, str],
    catalog: IndicatorCapabilityProvider,
    path: str,
    errors: list[StrategyValidationError],
) -> Operand:
    if value in aliases:
        return Operand(kind="indicator", value=aliases[value], label=value)
    if value in OHLCV_FIELDS:
        return Operand(kind="field", value=value, label=value)
    if catalog.supports_concrete(value):
        return Operand(kind="column", value=value, label=value)
    errors.append(make_error(path, f"unknown operand '{value}'", "unknown_operand"))
    return Operand(kind="literal", value=0, label=value)
