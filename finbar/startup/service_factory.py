"""Service factories and lazy infrastructure wiring.

This module is the composition-root helper used by REST and MCP adapters. It
keeps concrete infrastructure construction out of presentation modules.

Implementation is split across domain-specific modules:
  - _data_factories.py      — yfinance, Hyperliquid, fetch jobs, cache repos
  - _indicator_factories.py — Pandas TA, bar converters, feature calculators
  - _indicator_job_factories.py — job managers, runners, artifact access
  - _backtest_factories.py  — backtest runner, result store, backtest use cases
  - _optimization_factories.py — grid search, walk-forward, optimization jobs
  - _strategy_factories.py  — parsers, providers, schema, signal calculator
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from finbar_strategy_runtime.domain.entities.interval import Interval

# ── Backtest factories ──────────────────────────────────────────────────
from finbar.startup._backtest_factories import (  # noqa: F401
    get_backtest_result_store as _get_backtest_result_store,
    get_backtest_runner as _get_backtest_runner,
    make_apply_strategy_features_use_case as _make_apply_strategy_features_use_case,
    make_backtest_strategy_definition_use_case as _make_backtest_strategy_definition_use_case,
    make_get_backtest_equity_use_case as _make_get_backtest_equity_use_case,
    make_get_backtest_summary_use_case as _make_get_backtest_summary_use_case,
    make_get_backtest_trades_use_case as _make_get_backtest_trades_use_case,
    make_list_backtest_results_use_case as _make_list_backtest_results_use_case,
    make_run_backtest_use_case as _make_run_backtest_use_case,
    make_run_portfolio_backtest_use_case as _make_run_portfolio_backtest_use_case,
    make_store_backtest_result_use_case as _make_store_backtest_result_use_case,
)

# ── Data factories ──────────────────────────────────────────────────────
from finbar.startup._data_factories import (  # noqa: F401
    get_db as _get_db,
    get_fetcher as _get_fetcher,
    get_hl_fetcher as _get_hl_fetcher,
    get_hl_tickers as _get_hl_tickers,
    get_job_manager as _get_job_manager,
    make_delete_cached_use_case as _make_delete_cached_use_case,
    make_fetch_prices_use_case as _make_fetch_prices_use_case,
    make_get_latest_quote_use_case as _make_get_latest_quote_use_case,
    make_get_symbol_info_use_case as _make_get_symbol_info_use_case,
    make_list_cached_use_case as _make_list_cached_use_case,
    make_query_cached_use_case as _make_query_cached_use_case,
    _validate_source,
)

# ── Indicator (calculator) factories ────────────────────────────────────
from finbar.startup._indicator_factories import (  # noqa: F401
    get_bar_frame_converter as _get_bar_frame_converter,
    get_indicator_calculator as _get_indicator_calculator,
    get_strategy_feature_calculator as _get_strategy_feature_calculator,
    get_timeframe_bar_merger as _get_timeframe_bar_merger,
    make_apply_indicators_use_case as _make_apply_indicators_use_case,
)

# ── Indicator job factories ─────────────────────────────────────────────
from finbar.startup._indicator_job_factories import (  # noqa: F401
    get_indicator_job_manager as _get_indicator_job_manager,
    get_indicator_job_runner as _get_indicator_job_runner,
    get_strategy_pipeline_job_manager as _get_strategy_pipeline_job_manager,
    make_cancel_indicator_job_use_case as _make_cancel_indicator_job_use_case,
    make_compute_strategy_indicators_use_case as _make_compute_strategy_indicators_use_case,
    make_delete_artifact_use_case as _make_delete_artifact_use_case,
    make_describe_artifact_use_case as _make_describe_artifact_use_case,
    make_get_indicator_job_progress_use_case as _make_get_indicator_job_progress_use_case,
    make_get_indicator_job_results_use_case as _make_get_indicator_job_results_use_case,
    make_list_artifacts_use_case as _make_list_artifacts_use_case,
    make_query_artifact_bars_use_case as _make_query_artifact_bars_use_case,
    make_run_strategy_pipeline_use_case as _make_run_strategy_pipeline_use_case,
    make_start_indicator_job_use_case as _make_start_indicator_job_use_case,
    make_strategy_pipeline_job_runner as _make_strategy_pipeline_job_runner,
)

# ── Optimization factories ──────────────────────────────────────────────
from finbar.startup._optimization_factories import (  # noqa: F401
    get_optimization_job_manager as _get_optimization_job_manager,
    get_optimizer as _get_optimizer,
    get_walk_forward_optimizer as _get_walk_forward_optimizer,
    make_cancel_optimization_job_use_case as _make_cancel_optimization_job_use_case,
    make_get_optimization_job_progress_use_case as _make_get_optimization_job_progress_use_case,
    make_get_optimization_job_results_use_case as _make_get_optimization_job_results_use_case,
    make_start_optimization_job_use_case as _make_start_optimization_job_use_case,
    make_start_walk_forward_job_use_case as _make_start_walk_forward_job_use_case,
)

# ── Strategy factories ──────────────────────────────────────────────────
from finbar.startup._strategy_factories import (  # noqa: F401
    get_capability_service as _get_capability_service,
    get_json_strategy_factory as _get_json_strategy_factory,
    get_parser as _get_parser,
    get_schema_provider as _get_schema_provider,
    get_signal_calculator as _get_signal_calculator,
    make_delete_strategy_definition_use_case as _make_delete_strategy_definition_use_case,
    make_explain_strategy_definition_use_case as _make_explain_strategy_definition_use_case,
    make_save_strategy_definition_use_case as _make_save_strategy_definition_use_case,
    make_strategy_provider as _make_strategy_provider,
    make_validate_strategy_definition_use_case as _make_validate_strategy_definition_use_case,
)

if TYPE_CHECKING:
    from finbar.core.application.use_cases.compute_signals import (
        ComputeSignalsUseCase,
    )
    from finbar.core.application.use_cases.fetch_derivatives import (
        FetchDerivativesUseCase,
    )
    from finbar.core.domain.interfaces.derivatives_data_provider import (
        DerivativesDataProvider,
    )

# ── Derivatives / CoinGlass ────────────────────────────────────────────

_derivatives_provider: DerivativesDataProvider | None = None


def _get_derivatives_provider() -> DerivativesDataProvider:
    """Return the shared derivatives data provider (CoinGlass)."""
    global _derivatives_provider
    if _derivatives_provider is None:
        from finbar.infrastructure.services.coinglass_client import CoinGlassClient

        _derivatives_provider = CoinGlassClient()
    return _derivatives_provider


def _make_fetch_derivatives_use_case() -> FetchDerivativesUseCase:
    """Create a derivatives fetch use case with wiring."""
    from finbar.core.application.use_cases.fetch_derivatives import (
        FetchDerivativesUseCase,
    )
    from finbar.infrastructure.repositories.sql_coinglass_repository import (
        SqlCoinGlassRepository,
    )

    db = _get_db()
    return FetchDerivativesUseCase(
        provider=_get_derivatives_provider(),
        repository=SqlCoinGlassRepository(db),
    )


def _make_compute_signals_use_case() -> ComputeSignalsUseCase:
    """Create a signal computation use case with wiring."""
    from finbar.core.application.use_cases.compute_signals import (
        ComputeSignalsUseCase,
    )

    return ComputeSignalsUseCase(
        calculator=_get_signal_calculator(),
        converter=_get_bar_frame_converter(),
    )


# ── Validators ──────────────────────────────────────────────────────────


def _validate_interval(interval: str) -> Interval:
    """Validate and normalize an interval string."""
    try:
        return Interval(interval)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in Interval)
        raise ValueError(f"Unknown interval '{interval}'. Allowed: {allowed}") from exc


def _resolve_strategy(name: str, params: dict | None = None) -> object | None:
    """Resolve a strategy by name, checking built-ins and DB definitions."""
    db = _get_db()
    try:
        provider = _make_strategy_provider(db)
        return provider.create(name, params or {})
    finally:
        db.close()
