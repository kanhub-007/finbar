"""Architecture tests verifying Finbar consumes finbar_strategy_runtime package.

These tests ensure the refactored Finbar imports strategy runtime types from the
extracted package rather than from its own (now-redundant) source files.
"""

import ast
from pathlib import Path

FINBAR_SRC = Path(__file__).resolve().parents[2] / "finbar"

# Domain entities that were extracted to the package
EXTRACTED_ENTITIES = {
    "Condition",
    "ConditionGroup",
    "Operand",
    "IndicatorSpec",
    "FeatureSpec",
    "FormulaNode",
    "RiskSpec",
    "SideRules",
    "SignalResult",
    "StrategyDefinition",
    "StrategyDocument",
    "StrategyParameter",
    "StrategyMeta",
    "StrategyKind",
    "StrategyValidationError",
    "StrategyValidationResult",
    "TimeframeDeclaration",
    "InformativeTimeframe",
    "VolumeProfileResult",
    "Interval",
    "DataMode",
    "RiskFactor",
    "RsiZone",
    "MarketProfileResult",
    "ConfidenceScore",
}

# Domain interfaces that were extracted to the package
EXTRACTED_INTERFACES = {
    "indicator_capability_provider",
    "strategy_definition_parser",
    "condition_tree_visitor",
    "trading_strategy",
    "risk_price_calculator",
    "indicator_calculator",
    "bar_frame_converter",
    "timeframe_bar_merger",
    "strategy_definition_strategy_factory",
    "strategy_feature_calculator",
    "formula_feature_calculator",
    "signal_calculator",
}

# Parser/application services that were extracted to the package
EXTRACTED_SERVICES = {
    "strategy_definition_parser",
    "strategy_definition_serializer",
    "strategy_condition_parser",
    "strategy_condition_group_parser",
    "strategy_operand_parser",
    "strategy_definition_parse_helpers",
    "strategy_parameter_resolver",
    "strategy_indicator_resolver",
    "strategy_feature_resolver",
    "strategy_risk_resolver",
    "strategy_timeframe_resolver",
    "strategy_indicator_catalog",
    "strategy_capability_service",
    "strategy_limit_rule",
    "strategy_limit_rules",
    "strategy_warning_rule",
    "strategy_warning_rules",
    "max_indicators_limit_rule",
    "max_features_limit_rule",
    "max_parameters_limit_rule",
    "max_condition_depth_limit_rule",
    "no_exit_warning_rule",
    "no_stop_warning_rule",
    "serialize_group_visitor",
    "description_visitor",
    "required_column_collector",
    "feature_input_column_collector",
    "strategy_schema_provider",
}

# Infrastructure services that were extracted to the package
EXTRACTED_INFRA = {
    "condition_evaluator",
    "json_rule_based_strategy",
    "json_risk_price_calculator",
    "pandas_ta_indicator_calculator",
    "pandas_signal_calculator",
    "pandas_strategy_feature_calculator",
    "pandas_formula_feature_calculator",
    "pandas_bar_frame_converter",
    "pandas_timeframe_bar_merger",
    "bar_merger",
}


class TestFinbarConsumesPackage:
    """Verify Finbar imports extracted types from the package."""

    def test_extracted_entities_imported_from_package(self):
        """Domain entities that moved to the package should be imported from
        finbar_strategy_runtime, not from finbar.core.domain.entities."""
        violations = []

        for py_file in FINBAR_SRC.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue

            rel = str(py_file.relative_to(FINBAR_SRC.parent))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""

                    # Check domain entities
                    if module.startswith("finbar.core.domain.entities."):
                        entity_name = module.split(".")[-1]
                        # Only flag if this entity WAS extracted
                        for alias in node.names:
                            if alias.name in EXTRACTED_ENTITIES:
                                violations.append(
                                    f"{rel}: imports {alias.name} from {module}"
                                )

                    # Check domain interfaces
                    if module.startswith("finbar.core.domain.interfaces."):
                        iface_name = module.split(".")[-1]
                        if iface_name in EXTRACTED_INTERFACES:
                            violations.append(
                                f"{rel}: imports from {module}"
                            )

                    # Check parser services
                    if module.startswith("finbar.core.application.services."):
                        svc_name = module.split(".")[-1]
                        if svc_name in EXTRACTED_SERVICES:
                            violations.append(
                                f"{rel}: imports from {module}"
                            )

                    # Check infrastructure services
                    if module.startswith("finbar.infrastructure.services."):
                        svc_name = module.split(".")[-1]
                        if svc_name in EXTRACTED_INFRA:
                            violations.append(
                                f"{rel}: imports from {module}"
                            )

        assert len(violations) == 0, (
            "Files still importing extracted types from finbar instead of "
            "finbar_strategy_runtime:\n" + "\n".join(violations[:30])
            + (f"\n... and {len(violations) - 30} more" if len(violations) > 30 else "")
        )
