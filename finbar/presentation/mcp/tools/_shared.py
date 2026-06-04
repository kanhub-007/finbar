"""Shared helpers for MCP tools — lazy-initialized dependencies.

Pattern copied from kapsula/presentation/mcp/tools/_shared.py.
Module-level cached instances for expensive infrastructure (DB sessions,
use cases) — acceptable in the presentation layer per AGENTS.md.
"""

from sqlalchemy.orm import Session

from finbar.core.application.use_cases.delete_cached_prices import (
    DeleteCachedPricesUseCase,
)
from finbar.core.application.use_cases.fetch_prices import FetchPricesUseCase
from finbar.core.application.use_cases.get_latest_quote import (
    GetLatestQuoteUseCase,
)
from finbar.core.application.use_cases.get_symbol_info import GetSymbolInfoUseCase
from finbar.core.application.use_cases.list_cached_symbols import (
    ListCachedSymbolsUseCase,
)
from finbar.core.application.use_cases.query_cached_prices import (
    QueryCachedPricesUseCase,
)
from finbar.infrastructure.data.connection import SessionLocal
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
)
from finbar.infrastructure.repositories.sql_symbol_info_repository import (
    SqlSymbolInfoRepository,
)
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter
from finbar.infrastructure.services.yfinance_stock_fetcher import (
    YFinanceStockFetcher,
)

# ── Lazy-initialized singletons ───────────────────────────────────────────

_db: Session | None = None
_fetcher: YFinanceStockFetcher | None = None
_job_manager = None


def _get_db() -> Session:
    """Return a new SQLAlchemy session. Caller must close it."""
    return SessionLocal()


def _get_fetcher() -> YFinanceStockFetcher:
    """Lazy-init the yfinance fetcher with rate limiter."""
    global _fetcher
    if _fetcher is None:
        rate_limiter = YahooFinanceRateLimiter()
        _fetcher = YFinanceStockFetcher(rate_limiter=rate_limiter)
    return _fetcher


def _get_job_manager():
    """Lazy-init the fetch job manager."""
    global _job_manager
    if _job_manager is None:
        from finbar.presentation.mcp.fetch_job_manager import FetchJobManager

        _job_manager = FetchJobManager()
    return _job_manager


def _make_fetch_prices_use_case(db: Session):
    fetcher = _get_fetcher()
    cache = SqlPriceCacheRepository(db)
    return FetchPricesUseCase(fetcher=fetcher, cache=cache)


def _make_query_cached_use_case(db: Session):
    return QueryCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def _make_delete_cached_use_case(db: Session):
    return DeleteCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def _make_get_symbol_info_use_case(db: Session):
    fetcher = _get_fetcher()
    info_repo = SqlSymbolInfoRepository(db)
    return GetSymbolInfoUseCase(fetcher=fetcher, info_repo=info_repo)


def _make_list_cached_use_case(db: Session):
    return ListCachedSymbolsUseCase(cache=SqlPriceCacheRepository(db))


def _make_get_latest_quote_use_case(db: Session):
    fetcher = _get_fetcher()
    return GetLatestQuoteUseCase(fetcher=fetcher)
