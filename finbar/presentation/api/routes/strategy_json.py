"""Strategy JSON SDK API endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from finbar.core.application.dto.apply_strategy_features_request import (
    ApplyStrategyFeaturesRequest,
)
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.dto.save_strategy_definition_request import (
    SaveStrategyDefinitionRequest,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["Strategies"])


@router.get("/capabilities", summary="Get strategy SDK capabilities")
def get_capabilities():
    """Return supported operators, indicators, features, risk types, etc."""
    return _get_capability_service().get_capabilities()


@router.get("/schema", summary="Get strategy JSON Schema")
def get_schema():
    """Return the JSON Schema for strategy definitions."""
    return _get_schema_provider().get_schema()


@router.post("/validate", summary="Validate a strategy JSON definition")
def validate_strategy_json(definition: str, params: dict | None = None):
    """Validate a strategy definition and return diagnostics."""
    result = _make_validate_strategy_definition_use_case().execute(
        definition, params or {}
    )
    return {
        "valid": result.valid,
        "schema_version": (
            result.definition.schema_version if result.definition else "2.0"
        ),
        "name": result.definition.name if result.definition else "",
        "required_indicators": result.required_indicators,
        "required_columns": result.required_columns,
        "primary_required_indicators": result.primary_required_indicators,
        "informative_required_indicators": result.informative_required_indicators,
        "timeframe_intervals": result.timeframe_intervals,
        "errors": [
            {"path": e.path, "message": e.message, "code": e.code}
            for e in result.errors
        ],
        "warnings": [
            {"path": w.path, "message": w.message, "code": w.code}
            for w in result.warnings
        ],
    }


@router.post("/explain", summary="Explain a strategy in plain language")
def explain_strategy_json(definition: str, params: dict | None = None):
    """Return a human-readable explanation of a strategy."""
    result = _make_explain_strategy_definition_use_case().execute(
        definition, params or {}
    )
    return result


@router.post("/backtest", summary="Backtest a JSON strategy")
def backtest_strategy_json(
    definition: str,
    bars: list[dict] | None = None,
    symbol: str = "",
    interval: str = "",
    params: dict | None = None,
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
    bars_artifact_id: str = "",
    informative_bars: list[dict] | None = None,
    informative_bars_artifact_ids: dict[str, str] | None = None,
):
    """Backtest a JSON strategy against enriched bars or artifact IDs."""
    use_case = _make_backtest_strategy_definition_use_case()
    result = use_case.execute(
        BacktestStrategyDefinitionRequest(
            definition=definition,
            bars=bars or [],
            symbol=symbol,
            interval=interval,
            params=params or {},
            initial_cash=initial_cash,
            risk_per_trade=risk_per_trade,
            leverage=leverage,
            risk_mode=risk_mode,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            cap_explicit_size=cap_explicit_size,
            reject_oversized_explicit_orders=reject_oversized_explicit_orders,
            allow_negative_cash=allow_negative_cash,
            market_calendar=market_calendar,
            borrow_fee_annual_pct=borrow_fee_annual_pct,
            margin_mode=margin_mode,
            bars_artifact_id=bars_artifact_id,
            informative_bars=informative_bars,
            informative_bars_artifact_ids=informative_bars_artifact_ids or {},
        )
    )
    if not result.valid:
        errors = [{"path": e.path, "message": e.message} for e in result.errors]
        raise HTTPException(status_code=400, detail={"errors": errors})
    if result.result and result.result.error:
        raise HTTPException(status_code=400, detail=result.result.error)
    return {
        "valid": result.valid,
        "required_indicators": result.required_indicators,
        "result": result.result.__dict__ if result.result else None,
    }


@router.post("/features", summary="Apply strategy features")
def apply_strategy_features(
    definition: str,
    bars: list[dict],
    params: dict | None = None,
):
    """Calculate derived features declared in a strategy JSON document."""
    result = _make_apply_strategy_features_use_case().execute(
        ApplyStrategyFeaturesRequest(
            definition=definition,
            bars=bars,
            params=params or {},
        )
    )
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    return {
        "bar_count": result.bar_count,
        "features_applied": result.features_applied,
        "bars": result.bars,
    }


@router.post("/save", summary="Save a validated strategy")
def save_strategy_json(definition: str, name_override: str = ""):
    """Validate and persist a strategy JSON definition."""
    db = _get_db()
    try:
        result = _make_save_strategy_definition_use_case(db).execute(
            SaveStrategyDefinitionRequest(
                definition_json=definition,
                name_override=name_override or None,
            )
        )
    finally:
        db.close()
    return {
        "saved": result.saved,
        "name": result.name,
        "schema_version": result.schema_version,
        "error": result.error,
        "validation_errors": [
            {"path": e.path, "message": e.message, "code": e.code}
            for e in result.validation_errors
        ],
    }


@router.delete("/{name}", summary="Delete a saved strategy")
def delete_strategy_json(name: str):
    """Delete a previously saved strategy document by name."""
    db = _get_db()
    try:
        from finbar.core.application.dto.delete_strategy_definition_request import (
            DeleteStrategyDefinitionRequest,
        )

        result = _make_delete_strategy_definition_use_case(db).execute(
            DeleteStrategyDefinitionRequest(name=name)
        )
    finally:
        db.close()
    return {
        "deleted": result.deleted,
        "name": result.name,
        "error": result.error,
    }
