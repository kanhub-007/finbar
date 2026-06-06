"""RunBacktestUseCase — run a named strategy against historical OHLCV bars.

Depends on BacktestEngine and StrategyProvider. The provider creates a fresh
TradingStrategy per run so caller-provided strategy parameters are applied and
state does not leak between concurrent backtests.
"""

import logging

from finbar.core.application.backtest_result_mapper import result_dto_from_raw
from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.domain.entities.strategy_meta import StrategyMeta
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy

logger = logging.getLogger(__name__)


class RunBacktestUseCase:
    """Run a backtest with a named trading strategy against historical bars."""

    def __init__(
        self,
        engine: BacktestEngine,
        strategy_provider: StrategyProvider | dict[str, TradingStrategy],
        converter: BarFrameConverter,
    ):
        """Constructor injection — receives engine and strategy provider.

        Args:
            engine: BacktestEngine implementation.
            strategy_provider: StrategyProvider that creates fresh strategies.
                A dict registry is also accepted for backward-compatible tests.
            converter: Converts bar DTOs to the engine's frame type.
        """
        self._engine = engine
        self._strategy_provider = strategy_provider
        self._converter = converter

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
