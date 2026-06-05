"""Strategy CRUD MCP tools — create, list, get, update, delete strategies.

AI clients use these to define and manage custom trading strategies
without writing Python code. Strategies are stored in SQLite and
executed by the RuleBasedStrategy engine.
"""

import json
import logging

from fastmcp import FastMCP

from finbar.core.domain.entities.rule import Rule
from finbar.core.domain.entities.strategy_definition import StrategyDefinition
from finbar.startup.service_factory import _get_db, _make_run_backtest_use_case

logger = logging.getLogger(__name__)


def register_strategy_tools(mcp: FastMCP) -> None:
    """Register strategy CRUD MCP tools."""

    @mcp.tool(
        name="create_strategy",
        description=(
            "Create a new user-defined trading strategy from a JSON definition. "
            "The strategy is composed of entry rules (AND logic) and exit rules "
            "(OR logic). Each rule compares an indicator to a value. "
            "Supported operators: <, >, <=, >=, ==, !=, crosses_above, "
            "crosses_below. Values can be numbers or indicator names. "
            "Example definition:\n"
            '{"name": "trend_pullback", "direction": "long", '
            '"description": "Buy pullbacks in uptrends", '
            '"entry_rules": ['
            '{"indicator": "rsi_14", "operator": "<", "value": 40}, '
            '{"indicator": "close", "operator": ">", "value": "sma_50"}'
            "], "
            '"exit_rules": ['
            '{"indicator": "rsi_14", "operator": ">", "value": 70}'
            "], "
            '"stop_loss_atr_mult": 2.0, '
            '"take_profit_atr_mult": 3.0}'
        ),
    )
    def create_strategy(definition_json: str) -> str:
        """Create or update a strategy definition.

        Args:
            definition_json: JSON string with strategy definition fields.

        Returns:
            Confirmation message.
        """
        try:
            data = json.loads(definition_json)
        except json.JSONDecodeError as e:
            return f"Error: invalid JSON — {e}"

        try:
            definition = _parse_definition(data)
        except ValueError as e:
            return f"Error: {e}"

        db = _get_db()
        try:
            from finbar.infrastructure.repositories import (
                sql_strategy_definition_repository as sdr,
            )

            repo = sdr.SqlStrategyDefinitionRepository(db)
            repo.save(definition)
            return (
                f"Strategy '{definition.name}' saved.\n"
                f"Direction: {definition.direction}\n"
                f"Entry rules: {len(definition.entry_rules)}\n"
                f"Exit rules: {len(definition.exit_rules)}\n"
                f"Stop ATR mult: {definition.stop_loss_atr_mult}\n"
                f"Take profit ATR mult: {definition.take_profit_atr_mult}"
            )
        finally:
            db.close()

    @mcp.tool(
        name="list_strategies",
        description=(
            "List all available trading strategies — both built-in "
            "(sma_crossover, rsi_mean_reversion) and user-defined "
            "(created via create_strategy). Returns metadata for each."
        ),
    )
    def list_strategies(include_builtin: bool = True) -> str:
        """List all strategies.

        Args:
            include_builtin: Whether to include built-in Python strategies.

        Returns:
            JSON array of strategy metadata.
        """
        strategies = []

        # Built-in strategies
        if include_builtin:
            uc = _make_run_backtest_use_case()
            for meta in uc.list_strategies():
                strategies.append(
                    {
                        "name": meta.name,
                        "type": "builtin",
                        "description": meta.description,
                        "required_indicators": meta.required_indicators,
                        "default_params": meta.params,
                    }
                )

        # User-defined strategies from DB
        db = _get_db()
        try:
            from finbar.infrastructure.repositories import (
                sql_strategy_definition_repository as sdr,
            )
            from finbar.infrastructure.repositories import (
                sql_strategy_document_repository as sdd,
            )

            repo = sdr.SqlStrategyDefinitionRepository(db)
            for sdef in repo.list_all():
                indicators = _collect_indicators(sdef)
                strategies.append(
                    {
                        "name": sdef.name,
                        "type": "user_defined",
                        "description": sdef.description,
                        "direction": sdef.direction,
                        "entry_rules_count": len(sdef.entry_rules),
                        "exit_rules_count": len(sdef.exit_rules),
                        "required_indicators": indicators,
                        "stop_loss_atr_mult": sdef.stop_loss_atr_mult,
                        "take_profit_atr_mult": sdef.take_profit_atr_mult,
                    }
                )

            # v2 strategy documents
            v2_repo = sdd.SqlStrategyDocumentRepository(db)
            for doc in v2_repo.list_all():
                strategies.append(
                    {
                        "name": doc.name,
                        "type": "user_defined_v2",
                        "schema_version": doc.schema_version,
                        "description": doc.description,
                        "created_at": doc.created_at,
                        "updated_at": doc.updated_at,
                    }
                )
        finally:
            db.close()

        return json.dumps(strategies, indent=2)

    @mcp.tool(
        name="get_strategy",
        description=(
            "Get the full definition of a strategy by name. "
            "Works for both built-in and user-defined strategies. "
            "Returns all rules, parameters, and metadata."
        ),
    )
    def get_strategy(name: str) -> str:
        """Get a strategy's complete definition.

        Args:
            name: Strategy name.

        Returns:
            JSON string with full strategy definition.
        """
        # Check built-in
        uc = _make_run_backtest_use_case()
        if uc.has_strategy(name):
            meta = next(item for item in uc.list_strategies() if item.name == name)
            return json.dumps(
                {
                    "name": meta.name,
                    "type": "builtin",
                    "description": meta.description,
                    "required_indicators": meta.required_indicators,
                    "default_params": meta.params,
                },
                indent=2,
            )

        # Check DB
        db = _get_db()
        try:
            from finbar.infrastructure.repositories import (
                sql_strategy_definition_repository as sdr,
            )
            from finbar.infrastructure.repositories import (
                sql_strategy_document_repository as sdd,
            )

            repo = sdr.SqlStrategyDefinitionRepository(db)
            sdef = repo.find_by_name(name)
            if sdef is not None:
                return json.dumps(
                    {
                        "name": sdef.name,
                        "type": "user_defined",
                        "direction": sdef.direction,
                        "description": sdef.description,
                        "entry_rules": [
                            {
                                "indicator": r.indicator,
                                "operator": r.operator,
                                "value": r.value,
                            }
                            for r in sdef.entry_rules
                        ],
                        "exit_rules": [
                            {
                                "indicator": r.indicator,
                                "operator": r.operator,
                                "value": r.value,
                            }
                            for r in sdef.exit_rules
                        ],
                        "stop_loss_atr_mult": sdef.stop_loss_atr_mult,
                        "take_profit_atr_mult": sdef.take_profit_atr_mult,
                        "require_all_entry_rules": sdef.require_all_entry_rules,
                        "created_at": sdef.created_at,
                        "updated_at": sdef.updated_at,
                    },
                    indent=2,
                )

            # Check v2 documents
            v2_repo = sdd.SqlStrategyDocumentRepository(db)
            doc = v2_repo.find_by_name(name)
            if doc is not None:
                return json.dumps(
                    {
                        "name": doc.name,
                        "type": "user_defined_v2",
                        "schema_version": doc.schema_version,
                        "description": doc.description,
                        "definition_json": doc.definition_json,
                        "normalized_json": doc.normalized_json,
                        "created_at": doc.created_at,
                        "updated_at": doc.updated_at,
                    },
                    indent=2,
                )

            return f"Strategy '{name}' not found."
        finally:
            db.close()

    @mcp.tool(
        name="delete_strategy",
        description=(
            "Delete a user-defined strategy by name. "
            "Built-in strategies cannot be deleted. "
            "Returns confirmation or error."
        ),
    )
    def delete_strategy(name: str) -> str:
        """Delete a strategy definition.

        Args:
            name: Strategy name.

        Returns:
            Confirmation message.
        """
        # Prevent deleting built-ins
        uc = _make_run_backtest_use_case()
        if uc.has_strategy(name):
            return f"Cannot delete built-in strategy '{name}'."

        db = _get_db()
        try:
            from finbar.infrastructure.repositories import (
                sql_strategy_definition_repository as sdr,
            )

            repo = sdr.SqlStrategyDefinitionRepository(db)
            if repo.delete(name):
                return f"Strategy '{name}' deleted."
            return f"Strategy '{name}' not found."
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_definition(data: dict) -> StrategyDefinition:
    """Parse a JSON dict into a StrategyDefinition, with validation."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("name is required")

    direction = data.get("direction", "long")
    if direction not in ("long", "short", "both"):
        raise ValueError("direction must be 'long', 'short', or 'both'")

    entry_rules = _parse_rules(data.get("entry_rules", []))
    exit_rules = _parse_rules(data.get("exit_rules", []))

    return StrategyDefinition(
        name=name,
        direction=direction,
        description=data.get("description", ""),
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        stop_loss_atr_mult=float(data.get("stop_loss_atr_mult", 0)),
        take_profit_atr_mult=float(data.get("take_profit_atr_mult", 0)),
        require_all_entry_rules=data.get("require_all_entry_rules", True),
    )


def _parse_rules(raw: list[dict]) -> list[Rule]:
    """Parse a list of rule dicts."""
    rules = []
    for item in raw:
        indicator = item.get("indicator", "").strip()
        if not indicator:
            raise ValueError("each rule must have an 'indicator' field")
        operator = item.get("operator", "<")
        if operator not in (
            "<",
            ">",
            "<=",
            ">=",
            "==",
            "!=",
            "crosses_above",
            "crosses_below",
        ):
            raise ValueError(f"unknown operator '{operator}'")
        rules.append(
            Rule(
                indicator=indicator,
                operator=operator,
                value=item.get("value", 0),
            )
        )
    return rules


def _collect_indicators(sdef: StrategyDefinition) -> list[str]:
    """Collect unique indicator names from a StrategyDefinition."""
    indicators: list[str] = []
    for rule in sdef.entry_rules + sdef.exit_rules:
        if rule.indicator not in indicators and rule.indicator not in (
            "open",
            "high",
            "low",
            "close",
            "volume",
        ):
            indicators.append(rule.indicator)
    if sdef.stop_loss_atr_mult > 0 or sdef.take_profit_atr_mult > 0:
        if "atr" not in indicators:
            indicators.append("atr")
    return sorted(indicators)
