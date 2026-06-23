"""RunBacktestUseCase — run a named strategy against historical OHLCV bars.

Depends on BacktestEngine and StrategyProvider. The provider creates a fresh
TradingStrategy per run so caller-provided strategy parameters are applied and
state does not leak between concurrent backtests.
"""

import logging

from finbar_strategy_runtime.domain.entities.strategy_meta import StrategyMeta
from finbar_strategy_runtime.domain.interfaces import (
    strategy_definition_strategy_factory as strategy_factory_interface,
)
from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import (
    BarFrameConverter,
)
from finbar_strategy_runtime.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy
from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
    MultiTimeframeBarEnricher,
)

from finbar.core.application.backtest_result_mapper import result_dto_from_raw
from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.application.dto.backtest_strategy_definition_request import (
    BacktestStrategyDefinitionRequest,
)
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.backtest_input_validator import (
    BacktestInputValidator,
)
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.services.default_backtest_input_validator import (
    DefaultBacktestInputValidator,
)

logger = logging.getLogger(__name__)


class RunBacktestUseCase:
    """Run a backtest with a named trading strategy against historical bars."""

    def __init__(
        self,
        engine: BacktestEngine,
        strategy_provider: StrategyProvider | dict[str, TradingStrategy],
        converter: BarFrameConverter,
        parser: StrategyDefinitionParser | None = None,
        strategy_factory: (
            strategy_factory_interface.StrategyDefinitionStrategyFactory | None
        ) = None,
        enricher: MultiTimeframeBarEnricher | None = None,
        input_validator: BacktestInputValidator | None = None,
        strategy_definition_backtester: BacktestStrategyDefinitionUseCase | None = None,
    ):
        """Constructor injection — receives engine and strategy provider.

        Args:
            engine: BacktestEngine implementation.
            strategy_provider: StrategyProvider that creates fresh strategies.
                A dict registry is also accepted for backward-compatible tests.
            converter: Converts bar DTOs to the engine's frame type.
            parser: Optional JSON strategy parser for saved strategy definitions.
            strategy_factory: Optional factory for saved JSON strategy objects.
            enricher: Optional package enricher for raw-bar causal enrichment.
            input_validator: Optional validator for backtest bar inputs. When
                omitted a :class:`DefaultBacktestInputValidator` is used.
            strategy_definition_backtester: Fully wired delegate used to run
                saved JSON definitions through the causal live-parity path
                (with feature calculator, data validator, etc.). Built by the
                startup composition root — never assembled inline here.
        """
        self._engine = engine
        self._strategy_provider = strategy_provider
        self._converter = converter
        self._parser = parser
        self._strategy_factory = strategy_factory
        self._enricher = enricher
        self._input_validator = input_validator or DefaultBacktestInputValidator()
        self._strategy_definition_backtester = strategy_definition_backtester

    def list_strategies(self) -> list[StrategyMeta]:
        """Return metadata for available strategies."""
        if isinstance(self._strategy_provider, dict):
            return [
                strategy.meta()
                for _, strategy in sorted(self._strategy_provider.items())
            ]
        return self._strategy_provider.list_metadata()

    def has_strategy(self, name: str) -> bool:
        """Return True if the named strategy is available."""
        if isinstance(self._strategy_provider, dict):
            return name in self._strategy_provider
        return self._strategy_provider.exists(name)

    def execute(self, request: BacktestRequest) -> BacktestResultDTO:
        """Execute a backtest and return structured results.

        Args:
            request: BacktestRequest with bars, strategy name, params, and cash.

        Returns:
            BacktestResultDTO with performance metrics, trades, and equity curve.
        """
        if not request.bars:
            return BacktestResultDTO(error="No bars provided")

        validation = self._input_validator.validate(request.bars, request.interval)
        if not validation.valid:
            return BacktestResultDTO(error="; ".join(validation.errors))

        saved_json_result = self._try_saved_json_backtest(request)
        if saved_json_result is not None:
            return saved_json_result

        strategy = self._create_strategy(request.strategy_name, request.params)
        if strategy is None:
            available = ", ".join(meta.name for meta in self.list_strategies())
            return BacktestResultDTO(
                error=(
                    f"Unknown strategy '{request.strategy_name}'. "
                    f"Available: {available}"
                ),
            )

        try:
            df = self._converter.bars_to_frame(request.bars)
        except Exception as e:
            logger.warning("Failed to convert bars to DataFrame: %s", e)
            return BacktestResultDTO(error=f"Invalid bar data: {e}")

        try:
            raw_result = self._engine.run(
                df=df,
                strategy=strategy,
                initial_cash=request.initial_cash,
                leverage=request.execution.leverage_multiplier,
                risk_mode=request.execution.risk_mode,
                commission_pct=request.execution.commission_pct,
                slippage_pct=request.execution.slippage_pct,
                cap_explicit_size=request.execution.cap_explicit_size,
                reject_oversized_explicit_orders=(
                    request.execution.reject_oversized_explicit_orders
                ),
                allow_negative_cash=request.execution.allow_negative_cash,
                market_calendar=request.execution.market_calendar,
                borrow_fee_annual_pct=request.execution.borrow_fee_annual_pct,
                margin_mode=request.execution.margin_mode,
                maintenance_margin_pct=request.execution.maintenance_margin_pct,
                enable_funding=request.execution.enable_funding,
                funding_rate=request.execution.funding_rate,
                interval=request.interval,
                **request.params,
            )
        except Exception as e:
            logger.exception("Backtest engine failed")
            return BacktestResultDTO(
                strategy_name=request.strategy_name,
                error=f"Backtest error: {e}",
            )

        raw_result["symbol"] = request.symbol
        raw_result["interval"] = request.interval
        return result_dto_from_raw(raw_result)

    def _create_strategy(
        self,
        name: str,
        params: dict | None,
    ) -> TradingStrategy | None:
        """Create a strategy through the provider or compatibility registry."""
        if isinstance(self._strategy_provider, dict):
            return self._strategy_provider.get(name)
        return self._strategy_provider.create(name, params or {})

    def _try_saved_json_backtest(
        self,
        request: BacktestRequest,
    ) -> BacktestResultDTO | None:
        """Run saved JSON definitions through the fully wired live-parity delegate.

        Returns None when the provider has no saved JSON definition, when no
        delegate is wired, or when the saved strategy should fall back to the
        built-in strategy path.
        """
        if self._strategy_definition_backtester is None or isinstance(
            self._strategy_provider, dict
        ):
            return None
        definition = self._strategy_provider.definition_for(request.strategy_name)
        if definition is None:
            return None
        result = self._strategy_definition_backtester.execute(
            BacktestStrategyDefinitionRequest(
                definition=definition,
                bars=request.bars,
                informative_bars=request.informative_bars,
                execution=request.execution,
                symbol=request.symbol,
                interval=request.interval,
                params=request.params,
                initial_cash=request.initial_cash,
                enrichment_mode=request.enrichment_mode,
            )
        )
        if result.result is not None:
            return result.result
        message = "; ".join(error.message for error in result.errors)
        return BacktestResultDTO(
            strategy_name=request.strategy_name,
            symbol=request.symbol,
            interval=request.interval,
            error=message or "Saved strategy backtest failed",
        )
