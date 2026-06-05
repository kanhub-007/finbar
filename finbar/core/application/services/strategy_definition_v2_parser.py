"""StrategyDefinitionV2Parser — parse and validate agent JSON strategies."""

from __future__ import annotations

import json

from finbar.core.application.services.required_column_collector import (
    RequiredColumnCollector,
)
from finbar.core.application.services.strategy_condition_parser import (
    StrategyConditionParser,
)
from finbar.core.application.services.strategy_feature_resolver import (
    StrategyFeatureResolver,
)
from finbar.core.application.services.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar.core.application.services.strategy_indicator_resolver import (
    StrategyIndicatorResolver,
)
from finbar.core.application.services.strategy_parameter_resolver import (
    StrategyParameterResolver,
)
from finbar.core.application.services.strategy_risk_resolver import (
    StrategyRiskResolver,
)
from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar.core.domain.entities.strategy_validation_result import (
    StrategyValidationResult,
)
from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)
from finbar.core.domain.interfaces.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser as V2ParserInterface,
)

MAX_INDICATORS = 20
MAX_FEATURES = 20
MAX_CONDITION_DEPTH = 5
MAX_PARAMETERS = 20


class StrategyDefinitionV2Parser(V2ParserInterface):
    """Parse agent-authored JSON into canonical v2 strategy definitions."""

    def __init__(self, catalog: IndicatorCapabilityProvider | None = None):
        """Create a parser with injectable parsing collaborators."""
        self._catalog = catalog or StrategyIndicatorCatalog()
        self._parameter_resolver = StrategyParameterResolver()
        self._indicator_resolver = StrategyIndicatorResolver(self._catalog)
        self._feature_resolver = StrategyFeatureResolver(self._catalog)
        self._risk_resolver = StrategyRiskResolver(self._catalog)
        self._condition_parser = StrategyConditionParser(self._catalog)

    def parse(
        self,
        raw_definition: str | dict,
        param_overrides: dict | None = None,
    ) -> StrategyValidationResult:
        """Parse, normalize, and validate a v2 strategy definition."""
        errors: list[StrategyValidationError] = []
        data = self._load(raw_definition, errors)
        if data is None:
            return StrategyValidationResult(valid=False, errors=errors)

        name = self._validate_header(data, errors)
        params = self._parameter_resolver.parse(data.get("parameters", {}), errors)
        resolved_params = self._parameter_resolver.apply_overrides(
            params,
            param_overrides or {},
            errors,
        )
        indicators = self._indicator_resolver.parse(
            data.get("indicators", []),
            resolved_params,
            errors,
        )
        features = self._feature_resolver.parse(
            data.get("features", []),
            indicators,
            resolved_params,
            errors,
        )
        risk = self._risk_resolver.parse(data.get("risk"), indicators, errors)
        sides = self._condition_parser.parse_sides(
            data.get("sides"),
            indicators,
            features,
            resolved_params,
            errors,
        )
        if errors:
            return StrategyValidationResult(valid=False, errors=errors)

        definition = StrategyDefinitionV2(
            name=name,
            description=str(data.get("description", "")),
            parameters=params,
            resolved_params=resolved_params,
            indicators=indicators,
            features=features,
            risk=risk,
            sides=sides,
            metadata=_metadata(data),
        )
        warnings: list[StrategyValidationError] = []
        _add_strategy_warnings(definition, warnings)
        _enforce_limits(params, indicators, features, definition, errors)
        if errors:
            return StrategyValidationResult(valid=False, errors=errors)

        return StrategyValidationResult(
            valid=True,
            definition=definition,
            normalized=_serialize_definition(definition),
            required_indicators=[item.concrete_name for item in indicators],
            required_columns=RequiredColumnCollector().collect(definition),
            warnings=warnings,
        )

    def parse_definition(
        self,
        raw_definition: str | dict,
        param_overrides: dict | None = None,
    ):
        """Parse and return the canonical definition entity directly."""
        result = self.parse(raw_definition, param_overrides)
        return result.definition

    def _load(
        self,
        raw_definition: str | dict,
        errors: list[StrategyValidationError],
    ) -> dict | None:
        if isinstance(raw_definition, dict):
            return raw_definition
        try:
            data = json.loads(raw_definition)
        except json.JSONDecodeError as exc:
            errors.append(_err("$", f"Invalid JSON: {exc}", "invalid_json"))
            return None
        if not isinstance(data, dict):
            errors.append(_err("$", "strategy definition must be a JSON object"))
            return None
        return data

    def _validate_header(
        self,
        data: dict,
        errors: list[StrategyValidationError],
    ) -> str:
        if data.get("schema_version") != "2.0":
            errors.append(_err("$.schema_version", "schema_version must be '2.0'"))
        name = str(data.get("name", "")).strip()
        if not name:
            errors.append(_err("$.name", "name is required"))
        return name


def _metadata(data: dict) -> dict:
    raw = data.get("metadata", {})
    return raw if isinstance(raw, dict) else {}


def _err(
    path: str, message: str, code: str = "validation_error"
) -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code=code)


def _serialize_definition(definition: StrategyDefinitionV2) -> dict:
    """Serialize a canonical v2 definition to a JSON-serializable dict."""
    result: dict = {
        "schema_version": definition.schema_version,
        "name": definition.name,
    }
    if definition.description:
        result["description"] = definition.description

    if definition.parameters:
        result["parameters"] = {
            name: _serialize_parameter(p) for name, p in definition.parameters.items()
        }

    if definition.indicators:
        result["indicators"] = [
            {
                "name": i.name,
                "type": i.type,
                "concrete_name": i.concrete_name,
                "period": i.period,
                "source": i.source,
            }
            for i in definition.indicators
        ]

    if definition.features:
        result["features"] = [
            {
                "name": f.name,
                "type": f.type,
                "source": f.source,
                "window": f.window,
                "shift": f.shift,
            }
            for f in definition.features
        ]

    if definition.risk is not None:
        result["risk"] = {
            "stop_loss": {
                "type": definition.risk.stop_loss_type,
                "indicator": definition.risk.stop_indicator,
                "multiplier": definition.risk.stop_multiplier,
            },
            "take_profit": {
                "type": definition.risk.take_profit_type,
                "indicator": definition.risk.take_profit_indicator,
                "multiplier": definition.risk.take_profit_multiplier,
            },
        }

    if definition.sides:
        result["sides"] = {}
        for side, s in definition.sides.items():
            side_obj: dict = {"entry": {"condition": _serialize_group(s.entry)}}
            if s.exit is not None:
                side_obj["exit"] = {"condition": _serialize_group(s.exit)}
            result["sides"][side] = side_obj

    if definition.metadata:
        result["metadata"] = definition.metadata

    return result


def _serialize_parameter(param) -> dict:
    p: dict = {"type": param.type, "default": param.default}
    if param.minimum is not None:
        p["minimum"] = param.minimum
    if param.maximum is not None:
        p["maximum"] = param.maximum
    return p


def _serialize_group(group) -> dict:
    if group.kind == "condition" and group.condition is not None:
        c = group.condition
        entry: dict = {"left": c.left.value, "operator": c.operator}
        if c.right is not None:
            entry["right"] = c.right.value
        return entry
    result: dict = {group.kind: [_serialize_group(child) for child in group.children]}
    return result


# ---------------------------------------------------------------------------
# Warnings and limits
# ---------------------------------------------------------------------------


def _add_strategy_warnings(
    definition: StrategyDefinitionV2,
    warnings: list[StrategyValidationError],
) -> None:
    _warn_no_exits(definition, warnings)
    _warn_no_risk(definition, warnings)


def _warn_no_exits(
    definition: StrategyDefinitionV2,
    warnings: list[StrategyValidationError],
) -> None:
    for side, rules in definition.sides.items():
        if rules.exit is None:
            warnings.append(
                _w(
                    f"$.sides.{side}",
                    f"no exit condition defined for {side} side",
                    "no_exit",
                )
            )


def _warn_no_risk(
    definition: StrategyDefinitionV2,
    warnings: list[StrategyValidationError],
) -> None:
    if definition.risk is None or definition.risk.stop_loss_type == "none":
        warnings.append(
            _w(
                "$.risk",
                "no stop-loss defined — strategy may hold losing positions",
                "no_stop",
            )
        )


def _enforce_limits(
    params: dict,
    indicators: list,
    features: list,
    definition: StrategyDefinitionV2,
    errors: list[StrategyValidationError],
) -> None:
    if len(params) > MAX_PARAMETERS:
        errors.append(
            _err(
                "$.parameters",
                f"maximum {MAX_PARAMETERS} parameters allowed, got {len(params)}",
            )
        )
    if len(indicators) > MAX_INDICATORS:
        errors.append(
            _err(
                "$.indicators",
                f"maximum {MAX_INDICATORS} indicators allowed, got {len(indicators)}",
            )
        )
    if len(features) > MAX_FEATURES:
        errors.append(
            _err(
                "$.features",
                f"maximum {MAX_FEATURES} features allowed, got {len(features)}",
            )
        )
    for side, rules in definition.sides.items():
        depth = _condition_depth(rules.entry)
        if depth > MAX_CONDITION_DEPTH:
            errors.append(
                _err(
                    f"$.sides.{side}.entry.condition",
                    f"max depth {MAX_CONDITION_DEPTH} exceeded (got {depth})",
                )
            )
        if rules.exit is not None:
            depth = _condition_depth(rules.exit)
            if depth > MAX_CONDITION_DEPTH:
                errors.append(
                    _err(
                        f"$.sides.{side}.exit.condition",
                        f"max depth {MAX_CONDITION_DEPTH} exceeded (got {depth})",
                    )
                )


def _condition_depth(group) -> int:
    if group.kind == "condition":
        return 0
    return 1 + max((_condition_depth(child) for child in group.children), default=0)


def _w(path: str, message: str, code: str = "warning") -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code=code)
