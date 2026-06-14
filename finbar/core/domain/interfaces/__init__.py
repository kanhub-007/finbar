"""Domain interfaces — contracts for indicator calculation, trading
strategies, and backtest engines. All are abstract (ABC) — concrete
implementations live in infrastructure/services/."""

from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar_strategy_runtime.domain.interfaces.condition_tree_visitor import ConditionTreeVisitor
from finbar_strategy_runtime.domain.interfaces.indicator_calculator import IndicatorCalculator
from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)
from finbar_strategy_runtime.domain.interfaces.risk_price_calculator import RiskPriceCalculator
from finbar_strategy_runtime.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)
from finbar_strategy_runtime.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)
from finbar.core.domain.interfaces.strategy_provider import StrategyProvider
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy

__all__ = [
    "BacktestEngine",
    "BarFrameConverter",
    "ConditionTreeVisitor",
    "IndicatorCalculator",
    "IndicatorCapabilityProvider",
    "RiskPriceCalculator",
    "StrategyDefinitionStrategyFactory",
    "StrategyFeatureCalculator",
    "StrategyProvider",
    "TradingStrategy",
]
