"""ComputeStrategyIndicatorsUseCase — start jobs from a strategy definition."""

from dataclasses import dataclass, field
from typing import Any

from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)

from finbar.core.application.dto.compute_strategy_indicators_result import (
    ComputeStrategyIndicatorsResult,
)
from finbar.core.domain.interfaces.indicator_job_manager import IndicatorJobManager
from finbar.core.domain.interfaces.indicator_job_runner import IndicatorJobRunner

_BASE_COLUMNS = {"open", "high", "low", "close", "volume", "timestamp"}


def _merge_informative_indicators(
    declared: dict[str, list[str]], extras: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Merge declared informative indicators with condition-referenced extras.

    Each alias's declared indicators come first; condition-referenced columns
    that are not already declared are appended. Aliases present only in extras
    (no declared indicators) are also included.
    """
    merged: dict[str, list[str]] = {}
    for alias, indicators in declared.items():
        merged[alias] = list(indicators)
    for alias, extras_list in extras.items():
        for extra in extras_list:
            if extra not in merged.setdefault(alias, []):
                merged[alias].append(extra)
    return merged


@dataclass(frozen=True)
class _IndicatorInput:
    """Describes one indicator computation to start."""

    symbol: str
    source: str
    interval: str
    timeframe_alias: str
    indicators: list[str] = field(default_factory=list)


class ComputeStrategyIndicatorsUseCase:
    """Validate a strategy and start indicator jobs for every declared timeframe."""

    def __init__(
        self,
        parser: StrategyDefinitionParser,
        manager: IndicatorJobManager,
        runner: IndicatorJobRunner,
    ):
        """Create the use case with injected collaborators."""
        self._parser = parser
        self._manager = manager
        self._runner = runner

    async def execute(
        self,
        definition_json: str,
        symbol: str,
        source: str = "yfinance",
        params_json: dict[str, Any] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        enrichment_mode: str = "live_parity_streaming",
    ) -> ComputeStrategyIndicatorsResult:
        """Validate the strategy, determine required indicators, and start jobs."""
        params = params_json or {}
        validation = self._parser.parse(definition_json, params)
        if not validation.valid or validation.definition is None:
            return ComputeStrategyIndicatorsResult(
                strategy_name="",
                valid=False,
                errors=_diagnostics(validation.errors),
            )
        definition = validation.definition
        timeframes = definition.timeframes
        primary_interval = timeframes.primary if timeframes else "1d"
        # Condition columns that always belong to the primary timeframe.

        # Build per-timeframe lookups for MTF strategies in one pass.
        # _informative_map: column interval suffix -> alias, used to route
        # condition-referenced columns to the right job.
        # _alias_to_interval: alias -> declared interval, used to start each
        # informative job on its declared timeframe rather than a fallback.
        _informative_map: dict[str, str] = {}
        _alias_to_interval: dict[str, str] = {}
        if timeframes and timeframes.informative:
            for info in timeframes.informative:
                suffix = f"_{info.interval}"
                _informative_map[suffix] = info.alias
                _alias_to_interval[info.alias] = info.interval

        primary_indicators = list(validation.primary_required_indicators)
        # Collect condition-referenced columns per timeframe.
        _info_extras: dict[str, list[str]] = {}
        for col in validation.required_columns:
            if col in _BASE_COLUMNS:
                continue
            if col in primary_indicators:
                continue
            assigned = False
            for suffix, alias in _informative_map.items():
                if col.endswith(suffix):
                    base_name = col[: -len(suffix)]
                    if base_name not in _info_extras.setdefault(alias, []):
                        _info_extras[alias].append(base_name)
                    assigned = True
                    break
            if not assigned:
                primary_indicators.append(col)

        inputs = [
            _IndicatorInput(
                symbol=symbol.upper(),
                source=source,
                interval=primary_interval,
                timeframe_alias="primary",
                indicators=primary_indicators,
            )
        ]
        for alias, indicators in _merge_informative_indicators(
            validation.informative_required_indicators, _info_extras
        ).items():
            inputs.append(
                _IndicatorInput(
                    symbol=symbol.upper(),
                    source=source,
                    interval=_alias_to_interval.get(alias, "1d"),
                    timeframe_alias=alias,
                    indicators=indicators,
                )
            )
        primary_info: dict[str, Any] = {}
        informative_info: dict[str, dict[str, Any]] = {}
        for item in inputs:
            info = self._start_job(
                item,
                definition_json,
                params,
                start_date,
                end_date,
                enrichment_mode,
            )
            if item.timeframe_alias == "primary":
                primary_info = info
            else:
                informative_info[item.timeframe_alias] = info
        return ComputeStrategyIndicatorsResult(
            strategy_name=definition.name,
            valid=True,
            primary=primary_info,
            informative=informative_info,
            primary_required_indicators=validation.primary_required_indicators,
            informative_required_indicators={
                alias: list(indicators)
                for alias, indicators in (
                    validation.informative_required_indicators.items()
                )
            },
        )

    def _start_job(
        self,
        item: _IndicatorInput,
        definition_json: str,
        params: dict[str, Any],
        start_date: str | None,
        end_date: str | None,
        enrichment_mode: str = "batch_full_frame",
    ) -> dict[str, Any]:
        job = self._manager.start(
            {
                "symbol": item.symbol,
                "source": item.source,
                "interval": item.interval,
                "mode": "strategy_required",
                "indicators": item.indicators,
                "timeframe_alias": item.timeframe_alias,
                "start_date": start_date,
                "end_date": end_date,
                "enrichment_mode": enrichment_mode,
                "definition": definition_json,
                "params": dict(params),
            },
            self._runner.run,
        )
        return {
            "job_id": job.job_id,
            "status": job.status,
            "interval": item.interval,
            "timeframe_alias": item.timeframe_alias,
        }


def _diagnostics(errors) -> list[dict[str, str]]:
    return [
        {"path": error.path, "message": error.message, "code": error.code}
        for error in errors
    ]
