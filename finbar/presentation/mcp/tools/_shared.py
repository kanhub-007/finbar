"""Shared helpers for MCP tools — lazy-initialized dependencies.

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
from finbar.core.domain.entities.data_source import DataSource
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

_fetcher: YFinanceStockFetcher | None = None
_hl_fetcher: object | None = None  # HyperliquidFetcher, lazy-imported
_job_manager: object | None = None  # FetchJobManager, lazy-imported
_indicator_calc: object | None = None  # PandasTaIndicatorCalculator, lazy-imported
_bt_runner: object | None = None  # BacktestRunner, lazy-imported
_bt_registry: dict | None = None  # Strategy registry, lazy-imported
_apply_indicators_uc: object | None = None  # ApplyIndicatorsUseCase, lazy-imported
_run_backtest_uc: object | None = None  # RunBacktestUseCase, lazy-imported


def _get_db() -> Session:
    """Return a new SQLAlchemy session. Caller must close it."""
    return SessionLocal()


def _get_fetcher(source: str = "yfinance") -> YFinanceStockFetcher | object:
    """Lazy-init and return the appropriate fetcher for the source."""
    if source == DataSource.HYPERLIQUID:
        return _get_hl_fetcher()
    return _get_yf_fetcher()


def _get_yf_fetcher() -> YFinanceStockFetcher:
    """Lazy-init the yfinance fetcher with rate limiter."""
    global _fetcher
    if _fetcher is None:
        rate_limiter = YahooFinanceRateLimiter()
        _fetcher = YFinanceStockFetcher(rate_limiter=rate_limiter)
    return _fetcher


def _get_hl_fetcher() -> object:  # HyperliquidFetcher
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


def _get_job_manager():
    """Lazy-init the fetch job manager."""
    global _job_manager
    if _job_manager is None:
        from finbar.presentation.mcp.fetch_job_manager import FetchJobManager

        _job_manager = FetchJobManager()
    return _job_manager


def _make_fetch_prices_use_case(db: Session, source: str = "yfinance"):
    fetcher = _get_fetcher(source)
    cache = SqlPriceCacheRepository(db)
    return FetchPricesUseCase(fetcher=fetcher, cache=cache)


def _make_query_cached_use_case(db: Session):
    return QueryCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def _make_delete_cached_use_case(db: Session):
    return DeleteCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def _make_get_symbol_info_use_case(db: Session, source: str = "yfinance"):
    fetcher = _get_fetcher(source)
    info_repo = SqlSymbolInfoRepository(db)
    return GetSymbolInfoUseCase(fetcher=fetcher, info_repo=info_repo)


def _make_list_cached_use_case(db: Session):
    return ListCachedSymbolsUseCase(cache=SqlPriceCacheRepository(db))


def _make_get_latest_quote_use_case(db: Session, source: str = "yfinance"):
    fetcher = _get_fetcher(source)
    return GetLatestQuoteUseCase(fetcher=fetcher)


def _get_hl_tickers(market_type: str = "all"):
    """Get Hyperliquid ticker list from the fetcher."""
    fetcher = _get_hl_fetcher()
    if market_type == "spot":
        return fetcher.fetch_spot_tickers()
    elif market_type == "perp":
        return fetcher.fetch_perp_tickers()
    elif market_type == "hip3":
        return fetcher.fetch_hip3_tickers()
    else:
        spot = fetcher.fetch_spot_tickers()
        perp = fetcher.fetch_perp_tickers()
        hip3 = fetcher.fetch_hip3_tickers()
        return spot + perp + hip3


# ── Analysis use case factories ──────────────────────────────────────────


def _make_apply_indicators_use_case():
    """Lazy-init the ApplyIndicatorsUseCase with PandasTaIndicatorCalculator."""
    global _indicator_calc, _apply_indicators_uc
    if _apply_indicators_uc is None:
        from finbar.core.application.use_cases.apply_indicators import (
            ApplyIndicatorsUseCase,
        )
        from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        _indicator_calc = PandasTaIndicatorCalculator()
        _apply_indicators_uc = ApplyIndicatorsUseCase(_indicator_calc)
    return _apply_indicators_uc


def _make_run_backtest_use_case():
    """Lazy-init the RunBacktestUseCase with engine and strategy registry."""
    global _bt_runner, _bt_registry, _run_backtest_uc
    if _run_backtest_uc is None:
        from finbar.core.application.use_cases.run_backtest import (
            RunBacktestUseCase,
        )
        from finbar.infrastructure.services.backtest_runner import BacktestRunner
        from finbar.infrastructure.services.backtest_strategies.rsi_mean_reversion import (  # noqa: E501
            RsiMeanReversionStrategy,
        )
        from finbar.infrastructure.services.backtest_strategies.sma_crossover import (
            SmaCrossoverStrategy,
        )

        _bt_runner = BacktestRunner()
        _bt_registry = {
            "sma_crossover": SmaCrossoverStrategy(),
            "rsi_mean_reversion": RsiMeanReversionStrategy(),
        }
        _run_backtest_uc = RunBacktestUseCase(_bt_runner, _bt_registry)
    return _run_backtest_uc
