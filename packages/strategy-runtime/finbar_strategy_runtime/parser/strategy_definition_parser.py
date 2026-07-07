"""StrategyDefinitionParser — parse and validate agent JSON strategies."""

from __future__ import annotations

import json

import yaml

from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
)
from finbar_strategy_runtime.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar_strategy_runtime.domain.entities.strategy_validation_result import (
    StrategyValidationResult,
)
from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser as ParserInterface,
)
from finbar_strategy_runtime.parser._catalog_factory import default_catalog
from finbar_strategy_runtime.parser.required_column_collector import (
    RequiredColumnCollector,
)
from finbar_strategy_runtime.parser.strategy_condition_parser import (
    StrategyConditionParser,
)
from finbar_strategy_runtime.parser.strategy_definition_serializer import (
    StrategyDefinitionSerializer,
)
from finbar_strategy_runtime.parser.strategy_feature_resolver import (
    StrategyFeatureResolver,
)
from finbar_strategy_runtime.parser.strategy_indicator_resolver import (
    StrategyIndicatorResolver,
)
from finbar_strategy_runtime.parser.strategy_limit_rules import (
    DEFAULT_LIMIT_RULES,
    StrategyLimitRule,
)
from finbar_strategy_runtime.parser.strategy_parameter_resolver import (
    StrategyParameterResolver,
)
from finbar_strategy_runtime.parser.strategy_risk_resolver import (
    StrategyRiskResolver,
)
from finbar_strategy_runtime.parser.strategy_timeframe_resolver import (
    StrategyTimeframeResolver,
)
from finbar_strategy_runtime.parser.strategy_warning_rules import (
    DEFAULT_WARNING_RULES,
    StrategyWarningRule,
)


class StrategyDefinitionParser(ParserInterface):
    """Parse agent-authored JSON into canonical strategy definitions.

    Warning rules, limit rules, and serializer are injectable for OCP compliance.
    """

    def __init__(
        self,
        catalog: IndicatorCapabilityProvider | None = None,
        warning_rules: list[StrategyWarningRule] | None = None,
        limit_rules: list[StrategyLimitRule] | None = None,
        serializer: StrategyDefinitionSerializer | None = None,
    ):
        """Create a parser with injectable parsing collaborators.

        Args:
            catalog: Indicator capability provider for alias resolution.
            warning_rules: Rules that generate warnings for suspicious strategies.
            limit_rules: Rules that enforce SDK limits.
            serializer: Serializer for canonical dict output.
        """
        self._catalog = catalog or default_catalog()
        self._warning_rules = warning_rules or DEFAULT_WARNING_RULES
        self._limit_rules = limit_rules or DEFAULT_LIMIT_RULES
        self._serializer = serializer or StrategyDefinitionSerializer()
        self._parameter_resolver = StrategyParameterResolver()
        self._indicator_resolver = StrategyIndicatorResolver(self._catalog)
        self._feature_resolver = StrategyFeatureResolver(self._catalog)
        self._risk_resolver = StrategyRiskResolver(self._catalog)
        self._timeframe_resolver = StrategyTimeframeResolver()
        self._condition_parser = StrategyConditionParser(self._catalog)

    def parse(
        self,
        raw_definition: str | dict,
        param_overrides: dict | None = None,
    ) -> StrategyValidationResult:
        """Parse, normalize, and validate a strategy definition."""
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
        timeframes = self._timeframe_resolver.parse(data.get("timeframes"), errors)
        indicators = self._indicator_resolver.parse(
            data.get("indicators", []),
            resolved_params,
            errors,
            timeframes,
        )
        features = self._feature_resolver.parse(
            data.get("features", []),
            indicators,
            resolved_params,
            errors,
        )
        risk = self._risk_resolver.parse(
            data.get("risk"), indicators, resolved_params, errors
        )
        sides = self._condition_parser.parse_sides(
            data.get("sides"),
            indicators,
            features,
            resolved_params,
            errors,
        )
        if errors:
            return StrategyValidationResult(valid=False, errors=errors)

        definition = StrategyDefinition(
            name=name,
            description=str(data.get("description", "")),
            parameters=params,
            resolved_params=resolved_params,
            indicators=indicators,
            features=features,
            timeframes=timeframes,
            risk=risk,
            sides=sides,
            metadata=_metadata(data),
        )

        warnings = _collect_warnings(definition, self._warning_rules)
        limit_errors = _collect_limit_errors(
            definition, params, indicators, features, self._limit_rules
        )
        errors.extend(limit_errors)
        if errors:
            return StrategyValidationResult(valid=False, errors=errors)

        required_columns = RequiredColumnCollector().collect(definition)
        feature_names = {f.name for f in features}
        informative_intervals = _informative_intervals(definition)
        primary_required = _primary_required_indicators(
            indicators, required_columns, feature_names, self._catalog,
            informative_intervals,
        )
        # Surface condition-referenced columns nothing recognizes (likely
        # typos). Auto-resolution below must not mask them.
        unknown = _unknown_required_columns(
            required_columns, primary_required, feature_names, informative_intervals
        )
        if unknown:
            errors.append(
                _err(
                    "$.sides",
                    f"conditions reference unknown column(s) {unknown}: not OHLCV, "
                    f"not a declared indicator, not a feature, and not in the "
                    f"indicator catalog",
                )
            )
            return StrategyValidationResult(valid=False, errors=errors)

        return StrategyValidationResult(
            valid=True,
            definition=definition,
            normalized=self._serializer.serialize(definition),
            required_indicators=[item.column_name() for item in indicators],
            required_columns=required_columns,
            primary_required_indicators=primary_required,
            informative_required_indicators=_informative_required_indicators(
                indicators
            ),
            timeframe_intervals=_timeframe_intervals(definition),
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
        data, parse_error = _parse_any(raw_definition)
        if data is None:
            errors.append(_err("$", parse_error, "invalid_json"))
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


def _primary_required_indicators(
    indicators: list,
    required_columns: list[str],
    feature_names: set[str],
    catalog: IndicatorCapabilityProvider,
    informative_intervals: set[str],
) -> list[str]:
    """Concrete primary-timeframe indicators that must be computed.

    Unions explicitly declared indicators with condition-referenced columns
    the catalog recognizes as concrete indicators. Without the union, omitting
    the ``indicators[]`` array silently produced a bare-OHLCV backtest,
    because the indicator job runner trusts this field (not ``required_columns``)
    to decide what to compute. Feature-output columns are excluded -- they are
    produced by the feature calculator, not the indicator calculator.
    MTF-routed columns (e.g. ``sma_20_1h``) are excluded -- they belong to an
    informative timeframe and are resolved by its own job.
    """
    required: list[str] = []
    for item in indicators:
        if item.timeframe == "primary" and item.concrete_name not in required:
            required.append(item.concrete_name)
    for col in required_columns:
        if (
            col in _BASE_COLUMN_NAMES
            or col in required
            or col in feature_names
        ):
            continue
        if any(col.endswith(f"_{iv}") for iv in informative_intervals):
            continue
        if catalog.supports_concrete(col):
            required.append(col)
    return required


def _informative_intervals(definition: StrategyDefinition) -> set[str]:
    """Return declared informative interval strings (for MTF suffix detection)."""
    intervals: set[str] = set()
    if definition.timeframes and definition.timeframes.informative:
        for info in definition.timeframes.informative:
            intervals.add(str(info.interval))
    return intervals


def _unknown_required_columns(
    required_columns: list[str],
    primary_required: list[str],
    feature_names: set[str],
    informative_intervals: set[str],
) -> list[str]:
    """Return condition-referenced columns nothing recognizes (likely typos).

    A column is unknown if it is not OHLCV, not a declared or auto-resolved
    primary indicator, not a feature output, and not MTF-routed (i.e. does not
    end with a declared informative interval suffix like ``_1h``).
    """
    primary_set = set(primary_required)
    unknown: list[str] = []
    for col in required_columns:
        if (
            col in _BASE_COLUMN_NAMES
            or col in primary_set
            or col in feature_names
        ):
            continue
        if any(col.endswith(f"_{iv}") for iv in informative_intervals):
            continue
        unknown.append(col)
    return unknown


_BASE_COLUMN_NAMES = {"open", "high", "low", "close", "volume", "timestamp"}


def _informative_required_indicators(indicators: list) -> dict[str, list[str]]:
    required: dict[str, list[str]] = {}
    for item in indicators:
        if item.timeframe == "primary":
            continue
        values = required.setdefault(item.timeframe, [])
        if item.concrete_name not in values:
            values.append(item.concrete_name)
    return required


def _timeframe_intervals(definition: StrategyDefinition) -> dict[str, str]:
    if definition.timeframes is None:
        return {}
    intervals = {"primary": definition.timeframes.primary}
    for item in definition.timeframes.informative:
        intervals[item.alias] = item.interval
    return intervals


def _parse_any(raw: str) -> tuple[dict | None, str]:
    """Try JSON first, then YAML. Returns (data, error_message)."""
    try:
        return json.loads(raw), ""
    except json.JSONDecodeError:
        pass
    try:
        data = yaml.safe_load(raw)
        if isinstance(data, dict):
            return data, ""
        return None, "strategy definition must be a JSON or YAML object"
    except yaml.YAMLError as exc:
        return None, f"Invalid JSON or YAML: {exc}"


def _err(
    path: str, message: str, code: str = "validation_error"
) -> StrategyValidationError:
    return StrategyValidationError(path=path, message=message, code=code)


def _collect_warnings(
    definition: StrategyDefinition,
    rules: list[StrategyWarningRule],
) -> list[StrategyValidationError]:
    warnings: list[StrategyValidationError] = []
    for rule in rules:
        warning = rule.check(definition)
        if warning is not None:
            warnings.append(warning)
    return warnings


def _collect_limit_errors(
    definition: StrategyDefinition,
    params: dict,
    indicators: list,
    features: list,
    rules: list[StrategyLimitRule],
) -> list[StrategyValidationError]:
    errors: list[StrategyValidationError] = []
    for rule in rules:
        error = rule.check(definition, params, indicators, features)
        if error is not None:
            errors.append(error)
    return errors
