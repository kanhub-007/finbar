"""StrategyDefinition entity for agent-authored JSON strategies."""

from dataclasses import dataclass, field
from typing import Any

from finbar.core.domain.entities.feature_spec import FeatureSpec
from finbar.core.domain.entities.indicator_spec import IndicatorSpec
from finbar.core.domain.entities.risk_spec import RiskSpec
from finbar.core.domain.entities.side_rules import SideRules
from finbar.core.domain.entities.strategy_parameter import StrategyParameter


@dataclass(frozen=True)
class StrategyDefinition:
    """Canonical v2 strategy definition after parsing and parameter resolution.

    This entity is independent from persistence and presentation. It represents
    a validated strategy that can be explained or compiled to a TradingStrategy.
    """

    name: str
    """Unique strategy name."""

    sides: dict[str, SideRules]
    """Side-specific entry/exit rule trees keyed by long/short."""

    schema_version: str = "2.0"
    """Strategy schema version."""

    description: str = ""
    """Human-readable strategy description."""

    parameters: dict[str, StrategyParameter] = field(default_factory=dict)
    """Declared runtime parameters keyed by name."""

    resolved_params: dict[str, Any] = field(default_factory=dict)
    """Runtime parameter values after applying overrides."""

    indicators: list[IndicatorSpec] = field(default_factory=list)
    """Resolved strategy-local indicator aliases."""

    features: list[FeatureSpec] = field(default_factory=list)
    """Resolved derived feature declarations."""

    risk: RiskSpec | None = None
    """Optional structured risk settings."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Optional free-form metadata."""
