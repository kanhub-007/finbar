"""Strategy JSON SDK MCP tools for strategies."""

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
from finbar.presentation.mcp.presenters.strategy_json_presenter import (
    StrategyJsonPresenter,
)
from finbar.startup.service_factory import (
    _get_capability_service,
    _get_db,
    _get_schema_provider,
    _make_apply_strategy_features_use_case,
    _make_backtest_strategy_definition_use_case,
    _make_delete_strategy_definition_use_case,
    _make_explain_strategy_definition_use_case,
    _make_save_strategy_definition_use_case,
    _make_validate_strategy_definition_use_case,
)


def register_strategy_json_tools(mcp: FastMCP) -> None:
    """Register strategy JSON SDK tools."""

    @mcp.tool(
        name="get_strategy_capabilities",
        description=(
            "Return everything an AI needs to author a strategy JSON document. "
            "Includes supported operators (<, >, crosses_above, between, "
            "is_true, etc.), OHLCV fields (open, high, low, close, volume), "
            "supported indicator types (sma, ema, rsi, macd, atr, adx, vwap, "
            "bbands, rvol, ibs), supported feature types (rolling_max, "
            "rolling_min, body_pct, typical_price, ohlc4, etc.), supported "
            "risk types (atr, fixed_pct, risk_reward), and the exact concrete "
            "indicator names currently available (sma_20, rsi_14, atr, etc.). "
            "Call this first before writing any strategy JSON."
        ),
    )
    def get_strategy_capabilities() -> str:
        """Return machine-readable capabilities for agent strategy authoring."""
        return json.dumps(_get_capability_service().get_capabilities(), indent=2)

    @mcp.tool(
        name="get_strategy_schema",
        description=(
            "Return a JSON Schema describing the structure of a valid strategy "
            "definition. Use this for pre-validation or to understand required "
            "and optional fields before calling validate_strategy_json."
        ),
    )
    def get_strategy_schema() -> str:
        """Return a compact JSON Schema for strategy JSON."""
        return json.dumps(_get_schema_provider().get_schema(), indent=2)

    @mcp.tool(
        name="validate_strategy_json",
        description=(
            "Validate a strategy JSON definition. Returns whether the "
            "definition is valid, any path-specific validation errors "
            "(unknown indicators, unsupported operators, missing fields), "
            "the list of concrete indicator columns required (e.g., "
            "['sma_20', 'sma_50']), and the list of bar columns needed "
            "to execute (OHLCV + indicators + features). Does NOT fetch "
            "prices or calculate indicators — the agent must do those "
            "separately."
        ),
    )
    def validate_strategy_json(definition_json: str, params_json: str = "{}") -> str:
        """Validate a strategy JSON string and optional param overrides."""
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)
        result = _make_validate_strategy_definition_use_case().execute(
            definition_json, params
        )
        return json.dumps(StrategyJsonPresenter().validation_result(result), indent=2)

    @mcp.tool(
        name="explain_strategy_json",
        description=(
            "Explain a strategy JSON definition in plain language. "
            "Returns a Markdown-formatted explanation with sections for "
            "parameters, indicators, features, risk settings, and "
            "entry/exit conditions for each side. Useful for verifying "
            "that a generated strategy matches the intended behavior "
            "before running a backtest."
        ),
    )
    def explain_strategy_json(definition_json: str, params_json: str = "{}") -> str:
        """Explain a strategy JSON string and optional param overrides."""
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)
        result = _make_explain_strategy_definition_use_case().execute(
            definition_json, params
        )
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="apply_strategy_features",
        description=(
            "Calculate derived features declared in a strategy JSON document. "
            "Features are computed from OHLCV + indicator data and include "
            "rolling_max, rolling_min, rolling_mean, body_pct, range_pct, "
            "typical_price, ohlc4, and shift. Each feature can have a window "
            "and a lookback shift (e.g., rolling_max(high, 20).shift(1) for "
            "prior swing high). Returns enriched bars with feature columns "
            "added. Call this BEFORE backtest_strategy_json if the strategy "
            "declares features."
        ),
    )
    def apply_strategy_features(
        definition_json: str,
        bars_json: str,
        params_json: str = "{}",
    ) -> str:
        """Apply feature declarations to supplied bars."""
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
            "Run a backtest with a strategy JSON definition against "
            "already-enriched bars (including any indicators and features "
            "the strategy needs). Does NOT fetch prices or calculate "
            "indicators — the agent must call apply_indicators and "
            "apply_strategy_features BEFORE this tool. Returns full "
            "backtest results: total_return, sharpe_ratio, max_drawdown, "
            "win_rate, profit_factor, trades list (with entry/exit "
            "dates, prices, PnL, direction), and equity_curve (with "
            "date, close, portfolio value, drawdown, position). The "
            "equity curve includes close prices for overlay charting."
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
        """Backtest a strategy using bars supplied by the agent."""
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
            "Validate and persist a strategy JSON definition to the database. "
            "The definition is validated before saving. On success, the "
            "strategy appears in list_backtest_strategies and can be "
            "backtested by name via run_backtest. Returns validation errors "
            "if the definition is invalid. Use name_override to save under "
            "a different name than the one in the definition."
        ),
    )
    def save_strategy_json(
        definition_json: str,
        name_override: str = "",
    ) -> str:
        """Validate and save a strategy definition to the database."""
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
        description=(
            "Delete a previously saved strategy JSON document by name. "
            "Returns confirmation with the deleted name or an error if "
            "not found. Built-in strategies cannot be deleted."
        ),
    )
    def delete_strategy_json(name: str) -> str:
        """Delete a saved strategy document."""
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
