"""Strategy JSON SDK MCP tools for unsaved v2 strategies."""

import json

from fastmcp import FastMCP

from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
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
from finbar.startup.service_factory import _make_backtest_strategy_definition_use_case


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
        catalog = StrategyIndicatorCatalog()
        return json.dumps(
            {
                "schema_version": "2.0",
                "orchestration": [
                    "validate_strategy_json",
                    "fetch/query prices",
                    "apply_indicators separately",
                    "backtest_strategy_json with enriched bars",
                ],
                "backtest_calculates_indicators": False,
                "fields": ["timestamp", "open", "high", "low", "close", "volume"],
                "operators": [
                    "<",
                    ">",
                    "<=",
                    ">=",
                    "==",
                    "!=",
                    "crosses_above",
                    "crosses_below",
                    "between",
                    "not_between",
                    "is_true",
                    "is_false",
                    "exists",
                    "missing",
                ],
                "indicators": catalog.as_dict(),
            },
            indent=2,
        )

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
