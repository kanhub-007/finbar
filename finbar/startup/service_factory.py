"""Service factories and lazy infrastructure wiring.

This module is the composition-root helper used by REST and MCP adapters. It
keeps concrete infrastructure construction out of presentation modules.
"""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from finbar.core.application.services.strategy_capability_service import (
    StrategyCapabilityService,
)
from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.services.strategy_schema_provider import (
    StrategySchemaProvider,
)
from finbar.core.application.use_cases.apply_strategy_features import (
    ApplyStrategyFeaturesUseCase,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.cancel_indicator_job import (
    CancelIndicatorJobUseCase,
)
from finbar.core.application.use_cases.cancel_optimization_job import (
    CancelOptimizationJobUseCase,
)
from finbar.core.application.use_cases.delete_cached_prices import (
    DeleteCachedPricesUseCase,
)
from finbar.core.application.use_cases.delete_strategy_definition import (
    DeleteStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.explain_strategy_definition import (
    ExplainStrategyDefinitionUseCase,
)
from finbar.core.application.use_cases.fetch_prices import FetchPricesUseCase
from finbar.core.application.use_cases.get_indicator_job_progress import (
    GetIndicatorJobProgressUseCase,
)
from finbar.core.application.use_cases.get_indicator_job_results import (
    GetIndicatorJobResultsUseCase,
)
from finbar.core.application.use_cases.get_latest_quote import GetLatestQuoteUseCase
from finbar.core.application.use_cases.get_optimization_job_progress import (
    GetOptimizationJobProgressUseCase,
)
from finbar.core.application.use_cases.get_optimization_job_results import (
    GetOptimizationJobResultsUseCase,
)
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
from finbar.core.application.use_cases.start_indicator_job import (
    StartIndicatorJobUseCase,
)
from finbar.core.application.use_cases.start_optimization_job import (
    StartOptimizationJobUseCase,
)
from finbar.core.application.use_cases.start_walk_forward_job import (
    StartWalkForwardJobUseCase,
)
from finbar.core.application.use_cases.validate_strategy_definition import (
    ValidateStrategyDefinitionUseCase,
)
from finbar.core.domain.entities.data_source import DataSource
from finbar.core.domain.entities.interval import Interval
from finbar.core.domain.entities.optimizer_config import OptimizerConfig
from finbar.infrastructure.data.connection import SessionLocal
from finbar.infrastructure.repositories.sql_price_cache_repository import (
    SqlPriceCacheRepository,
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
from finbar.infrastructure.services.fetch_job_manager import FetchJobManager
from finbar.infrastructure.services.grid_search_optimizer import (
    GridSearchOptimizer,
)
from finbar.infrastructure.services.in_memory_indicator_job_manager import (
    InMemoryIndicatorJobManager,
)
from finbar.infrastructure.services.in_memory_optimization_job_manager import (
    InMemoryOptimizationJobManager,
)
from finbar.infrastructure.services.indicator_job_runner import (
    CachedPriceIndicatorJobRunner,
)
from finbar.infrastructure.services.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar.infrastructure.services.pandas_formula_feature_calculator import (
    PandasFormulaFeatureCalculator,
)
from finbar.infrastructure.services.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar.infrastructure.services.pandas_timeframe_bar_merger import (
    PandasTimeframeBarMerger,
)
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter
from finbar.infrastructure.services.strategy_definition_factory import (
    StrategyDefinitionFactory,
)
from finbar.infrastructure.services.walk_forward_optimizer import (
    WalkForwardOptimizer,
)
from finbar.infrastructure.services.yfinance_stock_fetcher import (
    YFinanceStockFetcher,
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
    from finbar.infrastructure.services.pandas_signal_calculator import (
        PandasSignalCalculator,
    )

_fetcher: YFinanceStockFetcher | None = None
_hl_fetcher: object | None = None
_job_manager: FetchJobManager | None = None
_indicator_job_manager: InMemoryIndicatorJobManager | None = None
_indicator_job_runner: CachedPriceIndicatorJobRunner | None = None
_optimization_job_manager: InMemoryOptimizationJobManager | None = None
_optimizer: GridSearchOptimizer | None = None
_walk_forward_optimizer: WalkForwardOptimizer | None = None
_indicator_calc: PandasTaIndicatorCalculator | None = None
_bar_frame_converter: PandasBarFrameConverter | None = None
_bt_runner: BacktestRunner | None = None
_builtin_strategy_provider: BuiltinStrategyProvider | None = None
_json_strategy_factory: StrategyDefinitionFactory | None = None
_strategy_feature_calculator: PandasStrategyFeatureCalculator | None = None
_parser: StrategyDefinitionParser | None = None
_capability_service: StrategyCapabilityService | None = None
_schema_provider: StrategySchemaProvider | None = None
_timeframe_bar_merger: PandasTimeframeBarMerger | None = None


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


def _get_indicator_job_manager() -> InMemoryIndicatorJobManager:
    """Lazy-init the indicator job manager."""
    global _indicator_job_manager
    if _indicator_job_manager is None:
        _indicator_job_manager = InMemoryIndicatorJobManager(
            session_factory=SessionLocal,
        )
    return _indicator_job_manager


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


def _make_start_indicator_job_use_case() -> StartIndicatorJobUseCase:
    """Create a use case for starting indicator jobs."""
    return StartIndicatorJobUseCase(
        _get_indicator_job_manager(),
        _get_indicator_job_runner(),
    )


def _get_indicator_job_runner() -> CachedPriceIndicatorJobRunner:
    """Return the shared indicator job runner."""
    global _indicator_job_runner
    if _indicator_job_runner is None:
        _indicator_job_runner = CachedPriceIndicatorJobRunner(
            session_factory=SessionLocal,
            manager=_get_indicator_job_manager(),
            indicator_calculator=_get_indicator_calculator(),
            converter=_get_bar_frame_converter(),
            feature_calculator=_get_strategy_feature_calculator(),
            parser=_get_parser(),
        )
    return _indicator_job_runner


def _make_get_indicator_job_progress_use_case() -> GetIndicatorJobProgressUseCase:
    """Create a use case for indicator job progress."""
    return GetIndicatorJobProgressUseCase(_get_indicator_job_manager())


def _make_get_indicator_job_results_use_case() -> GetIndicatorJobResultsUseCase:
    """Create a use case for paginated indicator job results."""
    return GetIndicatorJobResultsUseCase(_get_indicator_job_manager())


def _make_cancel_indicator_job_use_case() -> CancelIndicatorJobUseCase:
    """Create a use case for cancelling indicator jobs."""
    return CancelIndicatorJobUseCase(_get_indicator_job_manager())


def _get_optimization_job_manager() -> InMemoryOptimizationJobManager:
    """Lazy-init the optimization job manager."""
    global _optimization_job_manager
    if _optimization_job_manager is None:
        _optimization_job_manager = InMemoryOptimizationJobManager()
    return _optimization_job_manager


def _get_optimizer() -> GridSearchOptimizer:
    """Return the shared grid search optimizer."""
    global _optimizer
    if _optimizer is None:
        config = OptimizerConfig(
            parser=_get_parser(),
            engine=_get_backtest_runner(),
            converter=_get_bar_frame_converter(),
            strategy_factory=_get_json_strategy_factory(),
            manager=_get_optimization_job_manager(),
            artifact_provider=_get_indicator_job_manager(),
            timeframe_merger=_get_timeframe_bar_merger(),
            feature_calculator=_get_strategy_feature_calculator(),
        )
        _optimizer = GridSearchOptimizer(config)
    return _optimizer


def _make_start_optimization_job_use_case() -> StartOptimizationJobUseCase:
    """Create a use case for starting optimization jobs."""
    return StartOptimizationJobUseCase(
        _get_optimization_job_manager(),
        _get_optimizer(),
    )


def _make_start_walk_forward_job_use_case() -> StartWalkForwardJobUseCase:
    """Create a use case for starting walk-forward optimization jobs."""
    return StartWalkForwardJobUseCase(
        _get_optimization_job_manager(),
        _get_walk_forward_optimizer(),
    )


def _get_walk_forward_optimizer() -> WalkForwardOptimizer:
    """Return the shared walk-forward optimizer."""
    global _walk_forward_optimizer
    if _walk_forward_optimizer is None:
        config = OptimizerConfig(
            parser=_get_parser(),
            engine=_get_backtest_runner(),
            converter=_get_bar_frame_converter(),
            strategy_factory=_get_json_strategy_factory(),
            manager=_get_optimization_job_manager(),
            artifact_provider=_get_indicator_job_manager(),
            timeframe_merger=_get_timeframe_bar_merger(),
            feature_calculator=_get_strategy_feature_calculator(),
        )
        _walk_forward_optimizer = WalkForwardOptimizer(config)
    return _walk_forward_optimizer


def _make_get_optimization_job_progress_use_case() -> GetOptimizationJobProgressUseCase:
    """Create a use case for optimization job progress."""
    return GetOptimizationJobProgressUseCase(_get_optimization_job_manager())


def _make_get_optimization_job_results_use_case() -> GetOptimizationJobResultsUseCase:
    """Create a use case for optimization job results."""
    return GetOptimizationJobResultsUseCase(_get_optimization_job_manager())


def _make_cancel_optimization_job_use_case() -> CancelOptimizationJobUseCase:
    """Create a use case for cancelling optimization jobs."""
    return CancelOptimizationJobUseCase(_get_optimization_job_manager())


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
    """Create a use case for unsaved JSON strategy backtests."""
    return BacktestStrategyDefinitionUseCase(
        _get_backtest_runner(),
        _get_bar_frame_converter(),
        _get_json_strategy_factory(),
        parser=_get_parser(),
        timeframe_merger=_get_timeframe_bar_merger(),
        artifact_provider=_get_indicator_job_manager(),
        feature_calculator=_get_strategy_feature_calculator(),
    )


def _make_apply_strategy_features_use_case() -> ApplyStrategyFeaturesUseCase:
    """Create a use case for applying strategy feature declarations."""
    return ApplyStrategyFeaturesUseCase(
        _get_bar_frame_converter(),
        _get_strategy_feature_calculator(),
        parser=_get_parser(),
    )


def _get_backtest_runner() -> BacktestRunner:
    """Return the shared backtest runner instance."""
    global _bt_runner
    if _bt_runner is None:
        _bt_runner = BacktestRunner()
    return _bt_runner


def _get_json_strategy_factory() -> StrategyDefinitionFactory:
    """Return the JSON strategy factory."""
    global _json_strategy_factory
    if _json_strategy_factory is None:
        _json_strategy_factory = StrategyDefinitionFactory()
    return _json_strategy_factory


def _get_timeframe_bar_merger() -> PandasTimeframeBarMerger:
    """Return the shared timeframe bar merger."""
    global _timeframe_bar_merger
    if _timeframe_bar_merger is None:
        _timeframe_bar_merger = PandasTimeframeBarMerger()
    return _timeframe_bar_merger


def _get_strategy_feature_calculator() -> PandasStrategyFeatureCalculator:
    """Return the shared strategy feature calculator."""
    global _strategy_feature_calculator
    if _strategy_feature_calculator is None:
        _strategy_feature_calculator = PandasStrategyFeatureCalculator(
            formula_calculator=PandasFormulaFeatureCalculator(),
        )
    return _strategy_feature_calculator


# ── Signal interpretation ─────────────────────────────────────────────

_signal_calculator: "PandasSignalCalculator | None" = None


def _get_signal_calculator() -> "PandasSignalCalculator":
    """Return the shared signal interpretation calculator."""
    global _signal_calculator
    if _signal_calculator is None:
        from finbar.core.domain.services.confidence_scorer import ConfidenceScorer
        from finbar.infrastructure.services.pandas_signal_calculator import (
            PandasSignalCalculator,
        )

        _signal_calculator = PandasSignalCalculator(scorer=ConfidenceScorer())
    return _signal_calculator


def _make_compute_signals_use_case() -> "ComputeSignalsUseCase":
    """Create a signal computation use case with wiring."""
    from finbar.core.application.use_cases.compute_signals import (
        ComputeSignalsUseCase,
    )

    return ComputeSignalsUseCase(
        calculator=_get_signal_calculator(),
        converter=_get_bar_frame_converter(),
    )


def _get_parser() -> StrategyDefinitionParser:
    """Return the shared strategy JSON parser."""
    global _parser
    if _parser is None:
        _parser = StrategyDefinitionParser()
    return _parser


def _get_capability_service() -> StrategyCapabilityService:
    """Return the shared strategy capability service."""
    global _capability_service
    if _capability_service is None:
        _capability_service = StrategyCapabilityService()
    return _capability_service


def _get_schema_provider() -> StrategySchemaProvider:
    """Return the shared strategy schema provider."""
    global _schema_provider
    if _schema_provider is None:
        _schema_provider = StrategySchemaProvider()
    return _schema_provider


def _make_strategy_provider(db: Session | None = None) -> CompositeStrategyProvider:
    """Create the composite strategy provider used by backtesting tools."""
    global _builtin_strategy_provider
    if _builtin_strategy_provider is None:
        _builtin_strategy_provider = BuiltinStrategyProvider()

    providers = [_builtin_strategy_provider]
    if db is not None:
        doc_repo = SqlStrategyDocumentRepository(db)
        providers.append(DatabaseStrategyProvider(doc_repo, _get_parser()))
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
    """Create a use case for validating and saving strategy documents."""
    return SaveStrategyDefinitionUseCase(
        SqlStrategyDocumentRepository(db),
        parser=_get_parser(),
    )


def _make_delete_strategy_definition_use_case(
    db: Session,
) -> DeleteStrategyDefinitionUseCase:
    """Create a use case for deleting strategy documents."""
    return DeleteStrategyDefinitionUseCase(SqlStrategyDocumentRepository(db))


def _make_explain_strategy_definition_use_case() -> ExplainStrategyDefinitionUseCase:
    """Create a use case for explaining strategy JSON."""
    return ExplainStrategyDefinitionUseCase(parser=_get_parser())


def _make_validate_strategy_definition_use_case() -> ValidateStrategyDefinitionUseCase:
    """Create a use case for validating strategy JSON."""
    return ValidateStrategyDefinitionUseCase(_get_parser())


# ── Derivatives / CoinGlass ────────────────────────────────────────────

_derivatives_provider: "DerivativesDataProvider | None" = None


def _get_derivatives_provider() -> "DerivativesDataProvider":
    """Return the shared derivatives data provider (CoinGlass)."""
    global _derivatives_provider
    if _derivatives_provider is None:
        from finbar.infrastructure.services.coinglass_client import CoinGlassClient

        _derivatives_provider = CoinGlassClient()
    return _derivatives_provider


def _make_fetch_derivatives_use_case() -> "FetchDerivativesUseCase":
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
