"""StrategyIndicatorResolver — resolve indicator aliases."""

from typing import Any

from finbar.core.application.services.strategy_definition_parse_helpers import (
    OHLCV_FIELDS,
    make_error,
    resolve_expression,
)
from finbar.core.application.services.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar.core.domain.entities.indicator_spec import IndicatorSpec
from finbar.core.domain.entities.strategy_validation_error import (
    StrategyValidationError,
)
from finbar.core.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)


class StrategyIndicatorResolver:
    """Resolve strategy-local indicator aliases to concrete enrichment columns."""

    def __init__(self, catalog: IndicatorCapabilityProvider | None = None):
        """Create a resolver backed by an indicator capability catalog."""
        self._catalog = catalog or StrategyIndicatorCatalog()

    def parse(
        self,
        raw: Any,
        resolved_params: dict[str, Any],
        errors: list[StrategyValidationError],
    ) -> list[IndicatorSpec]:
        """Parse indicator declarations from a strategy JSON object."""
        if raw is None:
            return []
        if not isinstance(raw, list):
            errors.append(make_error("$.indicators", "indicators must be an array"))
            return []
        indicators: list[IndicatorSpec] = []
        used_aliases: set[str] = set()
        for index, item in enumerate(raw):
            self._parse_one(
                index, item, resolved_params, used_aliases, indicators, errors
            )
        return indicators

    def _parse_one(
        self,
        index: int,
        item: Any,
        resolved_params: dict[str, Any],
        used_aliases: set[str],
        indicators: list[IndicatorSpec],
        errors: list[StrategyValidationError],
    ) -> None:
        path = f"$.indicators[{index}]"
        if not isinstance(item, dict):
            errors.append(make_error(path, "indicator spec must be an object"))
            return
        alias = str(item.get("name", "")).strip()
        indicator_type = str(item.get("type", "")).lower().strip()
        if self._alias_invalid(alias, used_aliases, f"{path}.name", errors):
            return
        period = resolve_expression(
            item.get("period"), resolved_params, f"{path}.period", errors
        )
        if self._period_invalid(
            indicator_type,
            period,
            "period" in item,
            f"{path}.period",
            errors,
        ):
            return
        concrete = self._catalog.resolve(indicator_type, period)
        if concrete is None:
            errors.append(
                make_error(
                    path,
                    f"unsupported indicator type/period: {indicator_type}_{period}",
                    "unsupported_indicator",
                )
            )
            return
        indicators.append(
            IndicatorSpec(
                name=alias,
                type=indicator_type,
                period=period,
                raw_period=item.get("period"),
                source=str(item.get("source", "close")),
                concrete_name=concrete,
            )
        )
        used_aliases.add(alias)

    def _alias_invalid(
        self,
        alias: str,
        used_aliases: set[str],
        path: str,
        errors: list[StrategyValidationError],
    ) -> bool:
        if not alias:
            errors.append(make_error(path, "indicator name is required"))
            return True
        if alias in used_aliases or alias in OHLCV_FIELDS:
            errors.append(
                make_error(path, "indicator name must be unique and not an OHLCV field")
            )
            return True
        return False

    def _period_invalid(
        self,
        indicator_type: str,
        period: Any,
        period_supplied: bool,
        path: str,
        errors: list[StrategyValidationError],
    ) -> bool:
        if self._catalog.requires_period(indicator_type):
            if not isinstance(period, int) or isinstance(period, bool):
                errors.append(make_error(path, "period must resolve to an integer"))
                return True
            return False
        if period_supplied and period is not None:
            errors.append(
                make_error(
                    path,
                    f"indicator type '{indicator_type}' does not support "
                    "custom periods",
                    "unsupported_indicator_parameter",
                )
            )
            return True
        return False
