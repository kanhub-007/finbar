"""Compatibility re-exports for MCP tool factories.

Concrete wiring now lives in ``finbar.startup.service_factory`` so REST and MCP
adapters do not depend on each other.
"""

import json

from finbar.startup.service_factory import (  # noqa: F401
    _get_bar_frame_converter,
    _get_db,
    _get_fetcher,
    _get_hl_fetcher,
    _get_hl_tickers,
    _get_indicator_calculator,
    _get_indicator_job_manager,
    _get_job_manager,
    _get_optimization_job_manager,
    _make_apply_indicators_use_case,
    _make_apply_strategy_features_use_case,
    _make_cancel_indicator_job_use_case,
    _make_cancel_optimization_job_use_case,
    _make_compute_signals_use_case,
    _make_compute_strategy_indicators_use_case,
    _make_delete_artifact_use_case,
    _make_delete_cached_use_case,
    _make_describe_artifact_use_case,
    _make_fetch_derivatives_use_case,
    _make_fetch_prices_use_case,
    _make_get_backtest_equity_use_case,
    _make_get_backtest_summary_use_case,
    _make_get_backtest_trades_use_case,
    _make_get_indicator_job_progress_use_case,
    _make_get_indicator_job_results_use_case,
    _make_get_latest_quote_use_case,
    _make_get_optimization_job_progress_use_case,
    _make_get_optimization_job_results_use_case,
    _make_get_symbol_info_use_case,
    _make_list_artifacts_use_case,
    _make_list_backtest_results_use_case,
    _make_list_cached_use_case,
    _make_query_artifact_bars_use_case,
    _make_query_cached_use_case,
    _make_run_backtest_use_case,
    _make_run_strategy_pipeline_use_case,
    _make_start_indicator_job_use_case,
    _make_start_optimization_job_use_case,
    _make_start_walk_forward_job_use_case,
    _make_store_backtest_result_use_case,
    _make_validate_strategy_definition_use_case,
    _resolve_strategy,
    _validate_interval,
    _validate_source,
)


def _search_filter(
    items: list[dict],
    search: str | None,
    *,
    match_keys: tuple[str, ...],
    label: str,
) -> str | None:
    """Filter a list of dicts by case-insensitive search.

    Returns a JSON error string if no matches, or None if items were
    filtered successfully (mutates in-place by reassigning).
    Use pattern: filter_items = items; on match, items = match_list.
    """
    if not search:
        return None
    query = search.lower()
    matched = [
        item
        for item in items
        if any(query in str(item.get(key, "")).lower() for key in match_keys)
    ]
    if not matched:
        return json.dumps(
            {
                "message": (
                    f"No {label} matched '{search}'. "
                    "Try a different search or call without "
                    "search to see all available items."
                ),
                "count": 0,
                label: [],
            },
            indent=2,
        )
    items.clear()
    items.extend(matched)
    return None
