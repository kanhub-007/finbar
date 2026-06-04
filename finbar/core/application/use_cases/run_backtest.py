"""RunBacktestUseCase — run a named strategy against historical OHLCV bars.

Depends on BacktestEngine (Template Method) and a strategy registry
(dict of name → TradingStrategy). Uses Constructor DI + Registry pattern.

The AI client composes: get_cached_prices → apply_indicators → run_backtest.
"""

import logging

from finbar.core.application.bar_utils import bars_to_dataframe
from finbar.core.application.dto.backtest_request import BacktestRequest
from finbar.core.application.dto.backtest_result import BacktestResultDTO
from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy

logger = logging.getLogger(__name__)


class RunBacktestUseCase:
    """Run a backtest with a named trading strategy against historical bars.

    Strategies are registered by name in a dict (Registry pattern).
    The engine runs the bar-by-bar simulation; the use case converts
    the raw engine output into a BacktestResultDTO.
    """

    def __init__(
        self,
        engine: BacktestEngine,
        strategy_registry: dict[str, TradingStrategy],
    ):
        """Constructor injection — receives engine and strategy registry.

        Args:
            engine: BacktestEngine implementation (bar loop + metrics).
            strategy_registry: Dict mapping strategy_name → TradingStrategy
                instance. Built-in strategies are registered in the factory.
        """
        self._engine = engine
        self._registry = strategy_registry

    def execute(self, request: BacktestRequest) -> BacktestResultDTO:
        """Execute a backtest and return structured results.

        Args:
            request: BacktestRequest with bars, strategy name, params, cash.

        Returns:
            BacktestResultDTO with performance metrics, trades, equity curve.
        """
        # 1. Validate input
        if not request.bars:
            return BacktestResultDTO(error="No bars provided")

        strategy = self._registry.get(request.strategy_name)
        if strategy is None:
            available = ", ".join(sorted(self._registry.keys()))
            return BacktestResultDTO(
                error=(
                    f"Unknown strategy '{request.strategy_name}'. "
                    f"Available: {available}"
                ),
            )

        # 2. Convert bars to DataFrame
        try:
            df = bars_to_dataframe(request.bars)
        except Exception as e:
            logger.warning("Failed to convert bars to DataFrame: %s", e)
            return BacktestResultDTO(error=f"Invalid bar data: {e}")

        # 3. Run the engine
        try:
            raw_result = self._engine.run(
                df=df,
                strategy=strategy,
                initial_cash=request.initial_cash,
                **request.params,
            )
        except Exception as e:
            logger.exception("Backtest engine failed")
            return BacktestResultDTO(
                strategy_name=request.strategy_name,
                error=f"Backtest error: {e}",
            )

        # 4. Inject caller-provided metadata (engine doesn't know symbol/interval)
        raw_result["symbol"] = request.symbol
        raw_result["interval"] = request.interval

        # 5. Build DTO from engine output
        return BacktestResultDTO(
            strategy_name=raw_result.get("strategy_name", ""),
            symbol=raw_result.get("symbol", ""),
            interval=raw_result.get("interval", ""),
            start_date=raw_result.get("start_date", ""),
            end_date=raw_result.get("end_date", ""),
            bar_count=raw_result.get("bar_count", 0),
            initial_cash=raw_result.get("initial_cash", 0.0),
            final_value=raw_result.get("final_value", 0.0),
            total_return=raw_result.get("total_return", 0.0),
            annualized_return=raw_result.get("annualized_return"),
            total_trades=raw_result.get("total_trades", 0),
            winning_trades=raw_result.get("winning_trades", 0),
            losing_trades=raw_result.get("losing_trades", 0),
            win_rate=raw_result.get("win_rate", 0.0),
            max_drawdown=raw_result.get("max_drawdown", 0.0),
            sharpe_ratio=raw_result.get("sharpe_ratio", 0.0),
            sortino_ratio=raw_result.get("sortino_ratio", 0.0),
            profit_factor=raw_result.get("profit_factor", 0.0),
            calmar_ratio=raw_result.get("calmar_ratio", 0.0),
            trades=raw_result.get("trades", []),
            equity_curve=raw_result.get("equity_curve", []),
        )
