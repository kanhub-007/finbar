"""Backtest result projection helpers for compact MCP access."""

from __future__ import annotations

from typing import Any

_SUMMARY_FIELDS = [
    "strategy_name",
    "symbol",
    "interval",
    "start_date",
    "end_date",
    "bar_count",
    "initial_cash",
    "final_value",
    "total_return",
    "annualized_return",
    "annualization_factor",
    "annualization_warning",
    "total_trades",
    "winning_trades",
    "losing_trades",
    "win_rate",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "profit_factor",
    "calmar_ratio",
    "total_commission",
    "total_borrow_cost",
    "total_fees",
    "total_slippage",
    "realized_pnl",
    "cash",
    "ending_position_size",
    "reconciliation_error",
    "commission_pct",
    "slippage_pct",
    "position_sizing",
    "warmup_bars",
    "first_tradable",
    "error",
]


def compact_backtest_response(
    result_id: str,
    result: dict[str, Any],
    detail_level: str = "summary",
) -> dict[str, Any]:
    """Return a compact response envelope for a stored backtest result."""
    normalized = _normalize_detail_level(detail_level)
    payload = {
        "status": "completed" if not result.get("error") else "failed",
        "summary": summary_from_result(result),
        "ids": {"result_id": result_id},
        "counts": counts_from_result(result),
        "returned": {"trades": 0, "equity_points": 0, "analytics": 0},
        "access": access_for_result(result_id),
        "warnings": _warnings_from_result(result),
        "error": result.get("error"),
    }
    if normalized in {"sample", "full"}:
        payload.update(_sample_payload(result))
    if normalized == "full":
        payload["result"] = result
        payload["returned"] = {
            "trades": len(result.get("trades", [])),
            "equity_points": len(result.get("equity_curve", [])),
            "analytics": 1 if result.get("analytics") else 0,
        }
    return payload


def summary_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return metrics and diagnostics without large arrays."""
    summary = {field: result.get(field) for field in _SUMMARY_FIELDS if field in result}
    summary["trust_diagnostics"] = result.get("trust_diagnostics", {})
    summary["diagnostic_count"] = len(result.get("diagnostics", []))
    summary["analytics_available"] = bool(result.get("analytics"))
    summary["trade_summary"] = trade_summary(result.get("trades", []))
    return summary


def counts_from_result(result: dict[str, Any]) -> dict[str, int]:
    """Return counts for large payload sections."""
    return {
        "trades": len(result.get("trades", [])),
        "equity_points": len(result.get("equity_curve", [])),
        "diagnostics": len(result.get("diagnostics", [])),
        "analytics": 1 if result.get("analytics") else 0,
    }


def access_for_result(result_id: str) -> dict[str, str]:
    """Return MCP access hints for backtest detail retrieval."""
    return {
        "summary": f"get_backtest_summary('{result_id}')",
        "trades": f"get_backtest_trades('{result_id}', page=0, page_size=50)",
        "equity": f"get_backtest_equity('{result_id}', mode='daily')",
        "full": f"get_backtest_summary('{result_id}', detail_level='full')",
    }


def trade_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact trade statistics and top samples."""
    if not trades:
        return {
            "count": 0,
            "avg_pnl": 0.0,
            "avg_duration_bars": 0.0,
            "top_winners": [],
            "top_losers": [],
        }
    pnl_values = [
        float(trade.get("net_pnl", trade.get("pnl", 0.0)) or 0.0) for trade in trades
    ]
    durations = [int(trade.get("duration_bars", 0) or 0) for trade in trades]
    sorted_trades = sorted(
        trades,
        key=lambda item: float(item.get("net_pnl", item.get("pnl", 0.0)) or 0.0),
    )
    return {
        "count": len(trades),
        "avg_pnl": round(sum(pnl_values) / len(pnl_values), 4),
        "avg_duration_bars": round(sum(durations) / len(durations), 2),
        "top_winners": list(reversed(sorted_trades[-5:])),
        "top_losers": sorted_trades[:5],
    }


def page_items(
    items: list[dict[str, Any]],
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int, int, int, int]:
    """Return a clamped page of dict items and pagination metadata."""
    total = len(items)
    page_size = max(1, min(page_size, 1000))
    total_pages = (total + page_size - 1) // page_size if total else 0
    page = max(0, min(page, total_pages - 1)) if total_pages else 0
    start = page * page_size
    end = min(start + page_size, total)
    return items[start:end], page, page_size, total_pages, total


def sorted_trades(
    trades: list[dict[str, Any]],
    sort_by: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    """Return trades sorted by a safe field."""
    allowed = {
        "entry_date",
        "exit_date",
        "entry_price",
        "exit_price",
        "pnl",
        "net_pnl",
        "gross_pnl",
        "pnl_pct",
        "duration_bars",
    }
    field = sort_by if sort_by in allowed else "entry_date"
    reverse = sort_dir.lower() == "desc"
    return sorted(
        trades, key=lambda item: _sort_value(item.get(field)), reverse=reverse
    )


def equity_points(
    curve: list[dict[str, Any]],
    mode: str,
) -> list[dict[str, Any]]:
    """Return equity points for a requested access mode."""
    normalized = mode.lower().strip() or "daily"
    if normalized == "full" or normalized == "page":
        return curve
    if normalized == "none":
        return []
    if normalized == "weekly":
        return _downsample_by_prefix(curve, 10)
    if normalized == "drawdown_events":
        return _drawdown_events(curve)
    return _downsample_by_prefix(curve, 10 if _has_iso_dates(curve) else 0)


def _normalize_detail_level(detail_level: str) -> str:
    value = detail_level.lower().strip() if detail_level else "summary"
    return value if value in {"summary", "sample", "full"} else "summary"


def _sample_payload(result: dict[str, Any]) -> dict[str, Any]:
    trades = result.get("trades", [])
    equity = result.get("equity_curve", [])
    return {
        "samples": {
            "first_trades": trades[:5],
            "last_trades": trades[-5:],
            "first_equity_points": equity[:5],
            "last_equity_points": equity[-5:],
        },
        "returned": {
            "trades": min(len(trades), 10),
            "equity_points": min(len(equity), 10),
            "analytics": 0,
        },
    }


def _warnings_from_result(result: dict[str, Any]) -> list[str]:
    warnings = []
    annualization_warning = result.get("annualization_warning")
    if annualization_warning:
        warnings.append(str(annualization_warning))
    if result.get("diagnostics"):
        warnings.append("Execution diagnostics are available in the full result.")
    return warnings


def _sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (1, "")
    if isinstance(value, int | float | str):
        return (0, value)
    return (0, str(value))


def _downsample_by_prefix(
    curve: list[dict[str, Any]], prefix_len: int
) -> list[dict[str, Any]]:
    if prefix_len <= 0:
        return curve
    sampled: dict[str, dict[str, Any]] = {}
    for point in curve:
        key = str(point.get("date", ""))[:prefix_len]
        sampled[key] = point
    return list(sampled.values())


def _drawdown_events(curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    worst_by_bucket: dict[str, dict[str, Any]] = {}
    for point in curve:
        drawdown = float(point.get("drawdown", 0.0) or 0.0)
        if drawdown >= 0:
            continue
        bucket = str(point.get("date", ""))[:10]
        current = worst_by_bucket.get(bucket)
        if current is None or drawdown < float(current.get("drawdown", 0.0) or 0.0):
            worst_by_bucket[bucket] = point
    for key in sorted(worst_by_bucket):
        events.append(worst_by_bucket[key])
    return events


def _has_iso_dates(curve: list[dict[str, Any]]) -> bool:
    if not curve:
        return True
    return len(str(curve[0].get("date", ""))) >= 10
