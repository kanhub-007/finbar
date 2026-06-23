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
)

# ── Data factories ──────────────────────────────────────────────────────
from finbar.startup._data_factories import (  # noqa: F401
    get_db as _get_db,
)

# ── Indicator (calculator) factories ────────────────────────────────────
from finbar.startup._indicator_factories import (  # noqa: F401
    get_bar_frame_converter as _get_bar_frame_converter,
)

# ── Indicator job factories ─────────────────────────────────────────────
from finbar.startup._indicator_job_factories import (  # noqa: F401
    get_indicator_job_manager as _get_indicator_job_manager,
)

# ── Optimization factories ──────────────────────────────────────────────
from finbar.startup._optimization_factories import (  # noqa: F401
    get_optimization_job_manager as _get_optimization_job_manager,
)

# ── Strategy factories ──────────────────────────────────────────────────
from finbar.startup._strategy_factories import (  # noqa: F401
    get_capability_service as _get_capability_service,
)
from finbar.startup._strategy_factories import (
    get_signal_calculator as _get_signal_calculator,
)
from finbar.startup._strategy_factories import (
    make_strategy_provider as _make_strategy_provider,
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
