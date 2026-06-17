"""Data fetcher and cache factories — yfinance, Hyperliquid, fetch jobs."""

from sqlalchemy.orm import Session

from finbar.core.application.use_cases.delete_cached_prices import (
    DeleteCachedPricesUseCase,
)
from finbar.core.application.use_cases.fetch_prices import FetchPricesUseCase
from finbar.core.application.use_cases.get_latest_quote import GetLatestQuoteUseCase
from finbar.core.application.use_cases.get_symbol_info import GetSymbolInfoUseCase
from finbar.core.application.use_cases.list_cached_symbols import (
    ListCachedSymbolsUseCase,
)
from finbar.core.application.use_cases.query_cached_prices import (
    QueryCachedPricesUseCase,
)
from finbar.core.domain.entities.data_source import DataSource
from finbar.infrastructure.data.connection import SessionLocal
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
)
from finbar.infrastructure.repositories.sql_symbol_info_repository import (
    SqlSymbolInfoRepository,
)
from finbar.infrastructure.services.fetch_job_manager import FetchJobManager
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter
from finbar.infrastructure.services.yfinance_stock_fetcher import (
    YFinanceStockFetcher,
)

_fetcher: YFinanceStockFetcher | None = None
_hl_fetcher: object | None = None
_job_manager: FetchJobManager | None = None


def get_db() -> Session:
    """Return a new SQLAlchemy session. Caller must close it."""
    return SessionLocal()


def get_fetcher(source: str = "yfinance") -> YFinanceStockFetcher | object:
    """Lazy-init and return the appropriate fetcher for the source."""
    source_value = _validate_source(source)
    if source_value == DataSource.HYPERLIQUID:
        return get_hl_fetcher()
    return get_yf_fetcher()


def get_yf_fetcher() -> YFinanceStockFetcher:
    """Lazy-init the yfinance fetcher with rate limiter."""
    global _fetcher
    if _fetcher is None:
        rate_limiter = YahooFinanceRateLimiter()
        _fetcher = YFinanceStockFetcher(rate_limiter=rate_limiter)
    return _fetcher


def get_hl_fetcher() -> object:
    """Lazy-init the Hyperliquid fetcher with rate limiter."""
    global _hl_fetcher
    if _hl_fetcher is None:
        from finbar.infrastructure.services.hyperliquid_fetcher import (
            HyperliquidFetcher,
        )
        from finbar.infrastructure.services.hyperliquid_rate_limiter import (
            HyperliquidRateLimiter,
        )

        rate_limiter = HyperliquidRateLimiter()
        _hl_fetcher = HyperliquidFetcher(rate_limiter=rate_limiter)
    return _hl_fetcher


def get_job_manager() -> FetchJobManager:
    """Lazy-init the fetch job manager."""
    global _job_manager
    if _job_manager is None:
        _job_manager = FetchJobManager()
    return _job_manager


def get_hl_tickers(market_type: str = "all") -> list[dict]:
    """Get Hyperliquid ticker list from the fetcher."""
    fetcher = get_hl_fetcher()
    if market_type == "spot":
        return fetcher.fetch_spot_tickers()
    if market_type == "perp":
        return fetcher.fetch_perp_tickers()
    if market_type == "hip3":
        return fetcher.fetch_hip3_tickers()
    spot = fetcher.fetch_spot_tickers()
    perp = fetcher.fetch_perp_tickers()
    hip3 = fetcher.fetch_hip3_tickers()
    return spot + perp + hip3


def make_fetch_prices_use_case(
    db: Session,
    source: str = "yfinance",
) -> FetchPricesUseCase:
    """Create a fetch-prices use case for the selected data source."""
    fetcher = get_fetcher(source)
    cache = SqlPriceCacheRepository(db)
    return FetchPricesUseCase(fetcher=fetcher, cache=cache)


def make_query_cached_use_case(db: Session) -> QueryCachedPricesUseCase:
    """Create a cached-price query use case."""
    return QueryCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def make_delete_cached_use_case(db: Session) -> DeleteCachedPricesUseCase:
    """Create a cached-price deletion use case."""
    return DeleteCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def make_get_symbol_info_use_case(
    db: Session,
    source: str = "yfinance",
) -> GetSymbolInfoUseCase:
    """Create a symbol-info use case for the selected data source."""
    fetcher = get_fetcher(source)
    info_repo = SqlSymbolInfoRepository(db)
    return GetSymbolInfoUseCase(fetcher=fetcher, info_repo=info_repo)


def make_list_cached_use_case(db: Session) -> ListCachedSymbolsUseCase:
    """Create a cached-symbol list use case."""
    return ListCachedSymbolsUseCase(cache=SqlPriceCacheRepository(db))


def make_get_latest_quote_use_case(
    db: Session,
    source: str = "yfinance",
) -> GetLatestQuoteUseCase:
    """Create a latest-quote use case for the selected data source."""
    fetcher = get_fetcher(source)
    return GetLatestQuoteUseCase(fetcher=fetcher)


def _validate_source(source: str) -> DataSource:
    """Validate and normalize a data source string."""
    try:
        return DataSource(source)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in DataSource)
        raise ValueError(f"Unknown source '{source}'. Allowed: {allowed}") from exc
