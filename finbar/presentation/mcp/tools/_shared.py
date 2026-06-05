"""Compatibility re-exports for MCP tool factories.

Concrete wiring now lives in ``finbar.startup.service_factory`` so REST and MCP
adapters do not depend on each other.
"""

from finbar.startup.service_factory import (  # noqa: F401
    _get_bar_frame_converter,
    _get_db,
    _get_fetcher,
    _get_hl_fetcher,
    _get_hl_tickers,
    _get_indicator_calculator,
    _get_job_manager,
    _make_apply_indicators_use_case,
    _make_delete_cached_use_case,
    _make_fetch_prices_use_case,
    _make_get_latest_quote_use_case,
    _make_get_symbol_info_use_case,
    _make_list_cached_use_case,
    _make_query_cached_use_case,
    _make_run_backtest_use_case,
    _resolve_strategy,
    _validate_interval,
    _validate_source,
)
