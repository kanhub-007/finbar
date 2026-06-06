"""OptimizerConfig — configuration DTO for GridSearchOptimizer construction.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass, field
from typing import Any

from finbar.core.domain.interfaces.backtest_engine import BacktestEngine
from finbar.core.domain.interfaces.bar_frame_converter import BarFrameConverter
from finbar.core.domain.interfaces.indicator_artifact_provider import (
    IndicatorArtifactProvider,
)
from finbar.core.domain.interfaces.optimization_job_manager import (
    OptimizationJobManager,
)
from finbar.core.domain.interfaces.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.domain.interfaces.strategy_definition_strategy_factory import (
    StrategyDefinitionStrategyFactory,
)
from finbar.core.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)
from finbar.core.domain.interfaces.timeframe_bar_merger import TimeframeBarMerger


@dataclass(frozen=True)
class OptimizerConfig:
    """Wiring dependencies for GridSearchOptimizer.

    Groups all infrastructure collaborators into a single injectable config
    object, reducing constructor parameter count from 8 to 1.
    """

    parser: StrategyDefinitionParser
    engine: BacktestEngine
    converter: BarFrameConverter
    strategy_factory: StrategyDefinitionStrategyFactory
    manager: OptimizationJobManager
    artifact_provider: IndicatorArtifactProvider
    timeframe_merger: TimeframeBarMerger | None = None
    feature_calculator: StrategyFeatureCalculator | None = None
    max_combinations: int = 100
    initial_cash: float = 10000.0
    metric_aliases: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
