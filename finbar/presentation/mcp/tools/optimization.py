"""MCP optimization tools — parameter sweep / grid search."""

import json
from dataclasses import asdict

from fastmcp import FastMCP

from finbar.core.application.dto.start_optimization_job_request import (
    StartOptimizationJobRequest,
)

from ._shared import (
    _make_cancel_optimization_job_use_case,
    _make_get_optimization_job_progress_use_case,
    _make_get_optimization_job_results_use_case,
    _make_start_optimization_job_use_case,
)

_SUPPORTED_METRICS = frozenset(
    {
        "sharpe_ratio",
        "sortino_ratio",
        "total_return",
        "profit_factor",
        "win_rate",
        "calmar_ratio",
    }
)


def register_optimization_tools(mcp: FastMCP) -> None:
    """Register grid search optimization MCP tools."""

    @mcp.tool(
        name="start_optimization_job",
        description=(
            "Start a BACKGROUND optimization job. Given a "
            "strategy JSON with declared parameters, try combinations "
            "of the specified parameter ranges and rank by a metric. "
            "Use search_method='grid' (default) with min/max/step, "
            "or search_method='random' with min/max/random_count. "
            "Requires a completed indicator job artifact ID. "
            "Uses the same execution controls as direct backtests: "
            "risk_per_trade, leverage, commission, slippage, and "
            "explicit-size policy. Max 100 combinations. Poll with "
            "get_optimization_job_progress(job_id), retrieve ranked results "
            "with get_optimization_job_results(job_id)."
        ),
    )
    async def start_optimization_job(
        definition_json: str,
        bars_artifact_id: str,
        param_ranges_json: str,
        metric: str = "sharpe_ratio",
        informative_bars_artifact_ids_json: str = "{}",
        initial_cash: float = 10000.0,
        search_method: str = "grid",
        random_count: int = 20,
        interval: str = "",
        risk_per_trade: float = 0.02,
        leverage: float = 1.0,
        risk_mode: str = "fixed_equity_risk",
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
        cap_explicit_size: bool = True,
        reject_oversized_explicit_orders: bool = False,
        allow_negative_cash: bool = False,
        market_calendar: str = "equity_regular_hours",
    ) -> str:
        """Start a grid search optimization job and return its job id."""
        parsed = _parse_optimization_inputs(
            param_ranges_json, informative_bars_artifact_ids_json, metric
        )
        if "error" in parsed:
            return json.dumps(parsed)
        request = StartOptimizationJobRequest(
            definition=definition_json,
            bars_artifact_id=bars_artifact_id,
            param_ranges=parsed["param_ranges"],
            metric=parsed["metric"],
            informative_bars_artifact_ids=parsed["informative_artifact_ids"],
            initial_cash=initial_cash,
            search_method=search_method,
            random_count=random_count,
            interval=interval,
            risk_per_trade=risk_per_trade,
            leverage=leverage,
            risk_mode=risk_mode,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            cap_explicit_size=cap_explicit_size,
            reject_oversized_explicit_orders=reject_oversized_explicit_orders,
            allow_negative_cash=allow_negative_cash,
            market_calendar=market_calendar,
        )
        job = _make_start_optimization_job_use_case().execute(request)
        return json.dumps(
            {
                "job_id": job.job_id,
                "status": job.status,
                "metric": job.metric,
            },
            indent=2,
        )

    @mcp.tool(
        name="get_optimization_job_progress",
        description=(
            "Check an optimization job's status, metric, combinations "
            "done/total, and progress percentage."
        ),
    )
    def get_optimization_job_progress(job_id: str) -> str:
        """Return progress for an optimization job."""
        result = _make_get_optimization_job_progress_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="get_optimization_job_results",
        description=(
            "Return ranked optimization results from a completed job. "
            "Results are sorted by the chosen metric (best first). "
            "Each result includes the parameter combination and all "
            "backtest metrics."
        ),
    )
    def get_optimization_job_results(job_id: str) -> str:
        """Return ranked optimization results."""
        result = _make_get_optimization_job_results_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)

    @mcp.tool(
        name="cancel_optimization_job",
        description="Cancel a queued or running optimization job.",
    )
    def cancel_optimization_job(job_id: str) -> str:
        """Cancel an optimization job."""
        result = _make_cancel_optimization_job_use_case().execute(job_id)
        return json.dumps(asdict(result), indent=2, default=str)


def _parse_optimization_inputs(
    param_ranges_json: str,
    informative_bars_artifact_ids_json: str,
    metric: str,
) -> dict:
    if metric not in _SUPPORTED_METRICS:
        return {"error": f"metric must be one of {sorted(_SUPPORTED_METRICS)}"}
    try:
        param_ranges = json.loads(param_ranges_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid param_ranges_json: {exc}"}
    if not isinstance(param_ranges, dict):
        return {"error": "param_ranges_json must be a JSON object"}
    for name, spec in param_ranges.items():
        if not isinstance(spec, dict) or not all(
            key in spec for key in ("min", "max", "step")
        ):
            return {"error": f"Parameter '{name}' must have min, max, and step"}
    try:
        info_ids = json.loads(informative_bars_artifact_ids_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid informative_bars_artifact_ids_json: {exc}"}
    if not isinstance(info_ids, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in info_ids.items()
    ):
        return {
            "error": (
                "informative_bars_artifact_ids_json must be a JSON object of "
                "string values"
            )
        }
    return {
        "param_ranges": param_ranges,
        "metric": metric,
        "informative_artifact_ids": info_ids,
    }
