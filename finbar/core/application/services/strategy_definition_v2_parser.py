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


class StrategyDefinitionV2Parser:
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
        return StrategyValidationResult(
            valid=True,
            definition=definition,
            required_indicators=[item.concrete_name for item in indicators],
            required_columns=RequiredColumnCollector().collect(definition),
        )

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
