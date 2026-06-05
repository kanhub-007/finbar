"""Service factories and lazy infrastructure wiring.

This module is the composition-root helper used by REST and MCP adapters. It
keeps concrete infrastructure construction out of presentation modules.
"""

from sqlalchemy.orm import Session

from finbar.core.application.services.strategy_definition_v2_parser import (
    StrategyDefinitionV2Parser,
)
from finbar.core.application.use_cases.apply_strategy_features import (
    ApplyStrategyFeaturesUseCase,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.delete_cached_prices import (
    DeleteCachedPricesUseCase,
)
from finbar.core.application.use_cases.delete_strategy_definition import (
    DeleteStrategyDefinitionUseCase,
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
from finbar.core.application.use_cases.run_backtest import RunBacktestUseCase
from finbar.core.application.use_cases.save_strategy_definition import (
    SaveStrategyDefinitionUseCase,
)
from finbar.core.domain.entities.data_source import DataSource
from finbar.core.domain.entities.interval import Interval
from finbar.infrastructure.data.connection import SessionLocal
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
)
from finbar.infrastructure.repositories.sql_strategy_definition_repository import (
    SqlStrategyDefinitionRepository,
)
from finbar.infrastructure.repositories.sql_strategy_document_repository import (
    SqlStrategyDocumentRepository,
)
from finbar.infrastructure.repositories.sql_symbol_info_repository import (
    SqlSymbolInfoRepository,
)
from finbar.infrastructure.services.backtest_runner import BacktestRunner
from finbar.infrastructure.services.builtin_strategy_provider import (
    BuiltinStrategyProvider,
)
from finbar.infrastructure.services.composite_strategy_provider import (
    CompositeStrategyProvider,
)
from finbar.infrastructure.services.database_strategy_provider import (
    DatabaseStrategyProvider,
)
from finbar.infrastructure.services.database_v2_strategy_provider import (
    DatabaseV2StrategyProvider,
)
from finbar.infrastructure.services.fetch_job_manager import FetchJobManager
from finbar.infrastructure.services.json_strategy_definition_strategy_factory import (
    JsonStrategyDefinitionStrategyFactory,
)
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter
from finbar.infrastructure.services.yfinance_stock_fetcher import (
    YFinanceStockFetcher,
)

_fetcher: YFinanceStockFetcher | None = None
_hl_fetcher: object | None = None
_job_manager: FetchJobManager | None = None
_indicator_calc: PandasTaIndicatorCalculator | None = None
_bar_frame_converter: PandasBarFrameConverter | None = None
_bt_runner: BacktestRunner | None = None
_builtin_strategy_provider: BuiltinStrategyProvider | None = None
_json_strategy_factory: JsonStrategyDefinitionStrategyFactory | None = None
_strategy_feature_calculator: PandasStrategyFeatureCalculator | None = None
_v2_parser: StrategyDefinitionV2Parser | None = None


def _get_db() -> Session:
    """Return a new SQLAlchemy session. Caller must close it."""
    return SessionLocal()


def _validate_source(source: str) -> DataSource:
    """Validate and normalize a data source string."""
    try:
        return DataSource(source)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in DataSource)
        raise ValueError(f"Unknown source '{source}'. Allowed: {allowed}") from exc


def _validate_interval(interval: str) -> Interval:
    """Validate and normalize an interval string."""
    try:
        return Interval(interval)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in Interval)
        raise ValueError(f"Unknown interval '{interval}'. Allowed: {allowed}") from exc


def _get_fetcher(source: str = "yfinance") -> YFinanceStockFetcher | object:
    """Lazy-init and return the appropriate fetcher for the source."""
    source_value = _validate_source(source)
    if source_value == DataSource.HYPERLIQUID:
        return _get_hl_fetcher()
    return _get_yf_fetcher()


def _get_yf_fetcher() -> YFinanceStockFetcher:
    """Lazy-init the yfinance fetcher with rate limiter."""
    global _fetcher
    if _fetcher is None:
        rate_limiter = YahooFinanceRateLimiter()
        _fetcher = YFinanceStockFetcher(rate_limiter=rate_limiter)
    return _fetcher


def _get_hl_fetcher() -> object:
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


def _get_job_manager() -> FetchJobManager:
    """Lazy-init the fetch job manager."""
    global _job_manager
    if _job_manager is None:
        _job_manager = FetchJobManager()
    return _job_manager


def _make_fetch_prices_use_case(
    db: Session,
    source: str = "yfinance",
) -> FetchPricesUseCase:
    """Create a fetch-prices use case for the selected data source."""
    fetcher = _get_fetcher(source)
    cache = SqlPriceCacheRepository(db)
    return FetchPricesUseCase(fetcher=fetcher, cache=cache)


def _make_query_cached_use_case(db: Session) -> QueryCachedPricesUseCase:
    """Create a cached-price query use case."""
    return QueryCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def _make_delete_cached_use_case(db: Session) -> DeleteCachedPricesUseCase:
    """Create a cached-price deletion use case."""
    return DeleteCachedPricesUseCase(cache=SqlPriceCacheRepository(db))


def _make_get_symbol_info_use_case(
    db: Session,
    source: str = "yfinance",
) -> GetSymbolInfoUseCase:
    """Create a symbol-info use case for the selected data source."""
    fetcher = _get_fetcher(source)
    info_repo = SqlSymbolInfoRepository(db)
    return GetSymbolInfoUseCase(fetcher=fetcher, info_repo=info_repo)


def _make_list_cached_use_case(db: Session) -> ListCachedSymbolsUseCase:
    """Create a cached-symbol list use case."""
    return ListCachedSymbolsUseCase(cache=SqlPriceCacheRepository(db))


def _make_get_latest_quote_use_case(
    db: Session,
    source: str = "yfinance",
) -> GetLatestQuoteUseCase:
    """Create a latest-quote use case for the selected data source."""
    fetcher = _get_fetcher(source)
    return GetLatestQuoteUseCase(fetcher=fetcher)


def _get_hl_tickers(market_type: str = "all") -> list[dict]:
    """Get Hyperliquid ticker list from the fetcher."""
    fetcher = _get_hl_fetcher()
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


def _make_apply_indicators_use_case():
    """Lazy-init the ApplyIndicatorsUseCase with PandasTaIndicatorCalculator."""
    from finbar.core.application.use_cases.apply_indicators import (
        ApplyIndicatorsUseCase,
    )

    return ApplyIndicatorsUseCase(
        _get_indicator_calculator(),
        _get_bar_frame_converter(),
    )


def _get_indicator_calculator() -> PandasTaIndicatorCalculator:
    """Return the shared indicator calculator instance."""
    global _indicator_calc
    if _indicator_calc is None:
        _indicator_calc = PandasTaIndicatorCalculator()
    return _indicator_calc


def _get_bar_frame_converter() -> PandasBarFrameConverter:
    """Return the shared bar-frame converter instance."""
    global _bar_frame_converter
    if _bar_frame_converter is None:
        _bar_frame_converter = PandasBarFrameConverter()
    return _bar_frame_converter


def _make_run_backtest_use_case(db: Session | None = None) -> RunBacktestUseCase:
    """Create a RunBacktestUseCase with built-in and optional DB strategies."""
    return RunBacktestUseCase(
        _get_backtest_runner(),
        _make_strategy_provider(db),
        _get_bar_frame_converter(),
    )


def _make_backtest_strategy_definition_use_case() -> BacktestStrategyDefinitionUseCase:
    """Create a use case for unsaved v2 JSON strategy backtests."""
    return BacktestStrategyDefinitionUseCase(
        _get_backtest_runner(),
        _get_bar_frame_converter(),
        _get_json_strategy_factory(),
    )


def _make_apply_strategy_features_use_case() -> ApplyStrategyFeaturesUseCase:
    """Create a use case for applying v2 strategy feature declarations."""
    return ApplyStrategyFeaturesUseCase(
        _get_bar_frame_converter(),
        _get_strategy_feature_calculator(),
        parser=_get_v2_parser(),
    )


def _get_backtest_runner() -> BacktestRunner:
    """Return the shared backtest runner instance."""
    global _bt_runner
    if _bt_runner is None:
        _bt_runner = BacktestRunner()
    return _bt_runner


def _get_json_strategy_factory() -> JsonStrategyDefinitionStrategyFactory:
    """Return the v2 JSON strategy factory."""
    global _json_strategy_factory
    if _json_strategy_factory is None:
        _json_strategy_factory = JsonStrategyDefinitionStrategyFactory()
    return _json_strategy_factory


def _get_strategy_feature_calculator() -> PandasStrategyFeatureCalculator:
    """Return the shared strategy feature calculator."""
    global _strategy_feature_calculator
    if _strategy_feature_calculator is None:
        _strategy_feature_calculator = PandasStrategyFeatureCalculator()
    return _strategy_feature_calculator


def _get_v2_parser() -> StrategyDefinitionV2Parser:
    """Return the shared v2 strategy JSON parser."""
    global _v2_parser
    if _v2_parser is None:
        _v2_parser = StrategyDefinitionV2Parser()
    return _v2_parser


def _make_strategy_provider(db: Session | None = None) -> CompositeStrategyProvider:
    """Create the composite strategy provider used by backtesting tools."""
    global _builtin_strategy_provider
    if _builtin_strategy_provider is None:
        _builtin_strategy_provider = BuiltinStrategyProvider()

    providers = [_builtin_strategy_provider]
    if db is not None:
        repo = SqlStrategyDefinitionRepository(db)
        providers.append(DatabaseStrategyProvider(repo))
        v2_repo = SqlStrategyDocumentRepository(db)
        providers.append(DatabaseV2StrategyProvider(v2_repo, _get_v2_parser()))
    return CompositeStrategyProvider(providers)


def _resolve_strategy(name: str, params: dict | None = None) -> object | None:
    """Resolve a strategy by name, checking built-ins and DB definitions."""
    db = _get_db()
    try:
        provider = _make_strategy_provider(db)
        return provider.create(name, params or {})
    finally:
        db.close()


def _make_save_strategy_definition_use_case(
    db: Session,
) -> SaveStrategyDefinitionUseCase:
    """Create a use case for validating and saving v2 strategy documents."""
    return SaveStrategyDefinitionUseCase(
        SqlStrategyDocumentRepository(db),
        parser=_get_v2_parser(),
    )


def _make_delete_strategy_definition_use_case(
    db: Session,
) -> DeleteStrategyDefinitionUseCase:
    """Create a use case for deleting v2 strategy documents."""
    return DeleteStrategyDefinitionUseCase(SqlStrategyDocumentRepository(db))
