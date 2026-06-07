"""Strategy JSON SDK MCP tools for strategies."""

import json
from dataclasses import asdict

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
from finbar.core.domain.entities.execution_config import ExecutionConfig
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
    _make_store_backtest_result_use_case,
    _make_validate_strategy_definition_use_case,
)


def register_strategy_json_tools(mcp: FastMCP) -> None:
    """Register strategy JSON SDK tools."""

    @mcp.tool(
        name="get_strategy_capabilities",
        description=(
            "Return everything an AI needs to author a strategy JSON document. "
            "Includes: supported operators, OHLCV fields, indicator types "
            "(sma, ema, rsi, atr, adx, vwap, bbands, rvol, ibs, fallback), "
            "feature types (rolling_max, rolling_min, body_pct, formula), "
            "risk types (atr, fixed_pct, risk_reward), multi-timeframe support "
            "(primary + informative with column merging), period ranges "
            "for parameterized indicators, and concrete indicator names. "
            "Call this first before writing any strategy definition (JSON or YAML)."
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
            "Validate a strategy definition (JSON or YAML). Returns whether the "
            "definition is valid, any path-specific validation errors, "
            "the list of required concrete indicator columns, "
            "primary_required_indicators (for primary bars), "
            "informative_required_indicators (split by timeframe alias), "
            "and required bar columns. Does NOT fetch prices or calculate "
            "indicators — the agent must do those separately."
        ),
    )
    def validate_strategy_json(definition_json: str, params_json: str = "{}") -> str:
        """Validate a strategy definition string (JSON or YAML)."""
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
            "Explain a strategy definition (JSON or YAML) in plain language. "
            "Returns a Markdown-formatted explanation with sections for "
            "parameters, indicators, features, risk settings, and "
            "entry/exit conditions for each side. Useful for verifying "
            "that a generated strategy matches the intended behavior "
            "before running a backtest."
        ),
    )
    def explain_strategy_json(definition_json: str, params_json: str = "{}") -> str:
        """Explain a strategy definition string (JSON or YAML)."""
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
            "typical_price, ohlc4, shift, and formula (comparisons, "
            "arithmetic, logical and/or/not over indicators). Each feature "
            "can have a window and a lookback shift. Formula features use "
            "expression trees with ops like >, <, +, -, *, /, and, or, not. "
            "Returns indicator bars with feature columns added. Call this "
            "BEFORE backtest_strategy_json if the strategy declares features."
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
            "already-enriched bars. Features declared in the strategy "
            "are auto-computed — no separate apply_strategy_features call "
            "needed. Pass bars_artifact_id (preferred, avoids large JSON) "
            "or bars_json directly. For multi-timeframe strategies, also "
            "pass informative_bars_json or informative_bars_artifact_ids_json. "
            "You MUST call compute_indicators (and optionally compute_signals) "
            "on each timeframe BEFORE this tool. "
            "Supports execution controls including leverage, risk mode, "
            "commission, slippage, and explicit-size policy. Stores the full "
            "result server-side and returns a compact summary with result_id "
            "by default. Use get_backtest_trades() and get_backtest_equity() "
            "for paginated details. Set detail_level='full' only for export."
        ),
    )
    def backtest_strategy_json(
        definition_json: str,
        bars_json: str = "",
        symbol: str = "",
        interval: str = "",
        params_json: str = "{}",
        initial_cash: float = 10000.0,
        risk_per_trade: float = 0.02,
        leverage: float = 1.0,
        risk_mode: str = "fixed_equity_risk",
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
        cap_explicit_size: bool = True,
        reject_oversized_explicit_orders: bool = False,
        allow_negative_cash: bool = False,
        market_calendar: str = "equity_regular_hours",
        borrow_fee_annual_pct: float = 0.0,
        margin_mode: str = "simplified",
        informative_bars_json: str = "",
        bars_artifact_id: str = "",
        informative_bars_artifact_ids_json: str = "{}",
        detail_level: str = "summary",
    ) -> str:
        """Backtest a strategy using bars supplied by the agent or artifact id."""
        bars = _loads_array(bars_json, "bars_json") if bars_json else []
        if isinstance(bars, dict) and "error" in bars:
            return json.dumps(bars)
        params = _loads_object(params_json, "params_json")
        if "error" in params:
            return json.dumps(params)
        informative_bars = _loads_optional_informative_bars(informative_bars_json)
        if isinstance(informative_bars, dict) and "error" in informative_bars:
            return json.dumps(informative_bars)
        informative_artifacts = _loads_string_map(
            informative_bars_artifact_ids_json,
            "informative_bars_artifact_ids_json",
        )
        if "error" in informative_artifacts:
            return json.dumps(informative_artifacts)

        use_case = _make_backtest_strategy_definition_use_case()
        result = use_case.execute(
            BacktestStrategyDefinitionRequest(
                definition=definition_json,
                bars=bars,
                execution=ExecutionConfig(
                    leverage_multiplier=leverage,
                    risk_mode=risk_mode,
                    commission_pct=commission_pct,
                    slippage_pct=slippage_pct,
                    cap_explicit_size=cap_explicit_size,
                    reject_oversized_explicit_orders=(reject_oversized_explicit_orders),
                    allow_negative_cash=allow_negative_cash,
                    market_calendar=market_calendar,
                    borrow_fee_annual_pct=borrow_fee_annual_pct,
                    margin_mode=margin_mode,
                ),
                symbol=symbol,
                interval=interval,
                params=params,
                initial_cash=initial_cash,
                risk_per_trade=risk_per_trade,
                informative_bars=informative_bars,
                bars_artifact_id=bars_artifact_id,
                informative_bars_artifact_ids=informative_artifacts,
            )
        )
        return json.dumps(
            _strategy_backtest_response(result, detail_level),
            indent=2,
            default=str,
        )

    @mcp.tool(
        name="save_strategy_json",
        description=(
            "Validate and persist a strategy definition (JSON or YAML) to the database. "
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


def _strategy_backtest_response(result, detail_level: str) -> dict:
    """Return validation metadata plus a compact stored backtest response."""
    payload = {
        "valid": result.valid,
        "required_indicators": result.required_indicators,
        "primary_required_indicators": result.primary_required_indicators,
        "informative_required_indicators": result.informative_required_indicators,
        "missing_columns": result.missing_columns,
        "errors": [
            StrategyJsonPresenter().diagnostic(error) for error in result.errors
        ],
        "result": None,
    }
    if result.result is None:
        return payload
    stored = _make_store_backtest_result_use_case().execute(
        asdict(result.result),
        detail_level,
    )
    payload["result_id"] = stored.result_id
    payload["result"] = stored.response
    payload["store_error"] = stored.error
    return payload


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


def _loads_string_map(raw: str, name: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid {name}: {exc}"}
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        return {"error": f"{name} must be a JSON object of string values"}
    return value


def _loads_optional_informative_bars(raw: str) -> list[dict] | dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid informative_bars_json: {exc}"}
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if all(isinstance(item, list) for item in value.values()):
            return value
    return {
        "error": (
            "informative_bars_json must be a JSON array or an object mapping "
            "timeframe aliases to arrays"
        )
    }
