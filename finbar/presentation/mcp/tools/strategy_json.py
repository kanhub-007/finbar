"""Strategy JSON SDK MCP tools for unsaved v2 strategies."""

import json

from fastmcp import FastMCP

from finbar.core.application.dto.apply_strategy_features_request import (
    ApplyStrategyFeaturesRequest,
)
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.dto.save_strategy_definition_request import (
    SaveStrategyDefinitionRequest,
)
from finbar.core.application.services.strategy_capability_service import (
    StrategyCapabilityService,
)
from finbar.core.application.services.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser,
)
from finbar.core.application.services.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar.core.application.services.strategy_schema_provider import (
    StrategySchemaProvider,
)
from finbar.core.application.use_cases.explain_strategy_definition import (
    ExplainStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.validate_strategy_definition import (
    ValidateStrategyDefinitionUseCase,
)
from finbar.presentation.mcp.presenters.strategy_json_presenter import (
    StrategyJsonPresenter,
)
from finbar.startup.service_factory import (
    _get_db,
    _make_apply_strategy_features_use_case,
    _make_backtest_strategy_definition_use_case,
    _make_delete_strategy_definition_use_case,
    _make_save_strategy_definition_use_case,
)


def register_strategy_json_tools(mcp: FastMCP) -> None:
    """Register v2 strategy JSON SDK tools."""

    @mcp.tool(
        name="get_strategy_capabilities",
        description=(
            "Return supported v2 strategy JSON capabilities. Includes operators, "
            "OHLCV fields, supported concrete indicators, and notes that "
            "backtest_strategy_json expects already-enriched bars."
        ),
    )
    def get_strategy_capabilities() -> str:
        """Return machine-readable capabilities for agent strategy authoring."""
        return json.dumps(StrategyCapabilityService().get_capabilities(), indent=2)

    @mcp.tool(
        name="get_strategy_schema",
        description="Return a compact JSON Schema for v2 strategy definitions.",
    )
    def get_strategy_schema() -> str:
        """Return a compact JSON Schema for v2 strategy JSON."""
        return json.dumps(StrategySchemaProvider().get_schema(), indent=2)

    @mcp.tool(
        name="validate_strategy_json",
        description=(
            "Validate a v2 strategy JSON definition. Returns required indicator "
            "columns but does not fetch bars or calculate indicators."
        ),
    )
    def validate_strategy_json(definition_json: str, params_json: str = "{}") -> str:
        """Validate a v2 strategy JSON string and optional param overrides."""
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)
        result = ValidateStrategyDefinitionUseCase(
            StrategyDefinitionV2Parser(StrategyIndicatorCatalog())
        ).execute(definition_json, params)
        return json.dumps(StrategyJsonPresenter().validation_result(result), indent=2)

    @mcp.tool(
        name="explain_strategy_json",
        description="Explain a v2 strategy JSON definition in plain language.",
    )
    def explain_strategy_json(definition_json: str, params_json: str = "{}") -> str:
        """Explain a v2 strategy JSON string and optional param overrides."""
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)
        result = ExplainStrategyDefinitionUseCase(
            StrategyDefinitionV2Parser(StrategyIndicatorCatalog())
        ).execute(definition_json, params)
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="apply_strategy_features",
        description=(
            "Apply derived features declared in a v2 strategy JSON document. "
            "This is a separate enrichment step before backtest_strategy_json."
        ),
    )
    def apply_strategy_features(
        definition_json: str,
        bars_json: str,
        params_json: str = "{}",
    ) -> str:
        """Apply v2 feature declarations to supplied bars."""
        bars = _loads_array(bars_json, "bars_json")
        if isinstance(bars, dict) and "error" in bars:
            return json.dumps(bars)
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)
        result = _make_apply_strategy_features_use_case().execute(
            ApplyStrategyFeaturesRequest(
                definition=definition_json,
                bars=bars,
                params=params,
            )
        )
        return json.dumps(
            StrategyJsonPresenter().feature_result(result),
            indent=2,
            default=str,
        )

    @mcp.tool(
        name="backtest_strategy_json",
        description=(
            "Backtest an unsaved v2 strategy JSON against already-enriched bars. "
            "This tool does not fetch prices and does not calculate indicators; "
            "the AI agent must call apply_indicators first when required."
        ),
    )
    def backtest_strategy_json(
        definition_json: str,
        bars_json: str,
        symbol: str = "",
        interval: str = "",
        params_json: str = "{}",
        initial_cash: float = 10000.0,
    ) -> str:
        """Backtest a v2 strategy using bars supplied by the agent."""
        bars = _loads_array(bars_json, "bars_json")
        if isinstance(bars, dict) and "error" in bars:
            return json.dumps(bars)
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)

        use_case = _make_backtest_strategy_definition_use_case()
        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=definition_json,
                bars=bars,
                symbol=symbol,
                interval=interval,
                params=params,
                initial_cash=initial_cash,
            )
        )
        return json.dumps(StrategyJsonPresenter().backtest_result(result), indent=2)

    @mcp.tool(
        name="save_strategy_json",
        description=(
            "Validate and persist a v2 strategy JSON definition. "
            "Returns validation errors if the definition is invalid. "
            "On success, the strategy can be backtested by name."
        ),
    )
    def save_strategy_json(
        definition_json: str,
        name_override: str = "",
    ) -> str:
        """Validate and save a v2 strategy definition to the database."""
        db = _get_db()
        try:
            use_case = _make_save_strategy_definition_use_case(db)
            result = use_case.execute(
                SaveStrategyDefinitionRequest(
                    definition_json=definition_json,
                    name_override=name_override or None,
                )
            )
            return json.dumps(
                {
                    "saved": result.saved,
                    "name": result.name,
                    "schema_version": result.schema_version,
                    "error": result.error,
                    "validation_errors": [
                        {
                            "path": e.path,
                            "message": e.message,
                            "code": e.code,
                        }
                        for e in result.validation_errors
                    ],
                },
                indent=2,
            )
        finally:
            db.close()

    @mcp.tool(
        name="delete_strategy_json",
        description="Delete a saved v2 strategy document by name.",
    )
    def delete_strategy_json(name: str) -> str:
        """Delete a saved v2 strategy document."""
        db = _get_db()
        try:
            from finbar.core.application.dto.delete_strategy_definition_request import (
                DeleteStrategyDefinitionRequest,
            )

            use_case = _make_delete_strategy_definition_use_case(db)
            result = use_case.execute(DeleteStrategyDefinitionRequest(name=name))
            return json.dumps(
                {
                    "deleted": result.deleted,
                    "name": result.name,
                    "error": result.error,
                },
                indent=2,
            )
        finally:
            db.close()


def _loads_object(raw: str, name: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid {name}: {exc}"}
    if not isinstance(value, dict):
        return {"error": f"{name} must be a JSON object"}
    return value


def _loads_array(raw: str, name: str) -> list[dict] | dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid {name}: {exc}"}
    if not isinstance(value, list):
        return {"error": f"{name} must be a JSON array"}
    return value
