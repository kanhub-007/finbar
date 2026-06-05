"""StrategyDefinitionV2Serializer — serialize canonical definitions to dict."""

from finbar.core.application.services.serialize_group_visitor import (
    SerializeGroupVisitor,
)
from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2


class StrategyDefinitionV2Serializer:
    """Serialize a canonical v2 strategy definition to a JSON-serializable dict."""

    def serialize(self, definition: StrategyDefinitionV2) -> dict:
        """Return a canonical dict representation of the definition."""
        result: dict = {
            "schema_version": definition.schema_version,
            "name": definition.name,
        }
        if definition.description:
            result["description"] = definition.description

        if definition.parameters:
            result["parameters"] = {
                name: _serialize_parameter(p)
                for name, p in definition.parameters.items()
            }

        if definition.indicators:
            result["indicators"] = [
                {
                    "name": i.name,
                    "type": i.type,
                    "concrete_name": i.concrete_name,
                    "period": i.period,
                    "source": i.source,
                }
                for i in definition.indicators
            ]

        if definition.features:
            result["features"] = [
                {
                    "name": f.name,
                    "type": f.type,
                    "source": f.source,
                    "window": f.window,
                    "shift": f.shift,
                }
                for f in definition.features
            ]

        if definition.risk is not None:
            result["risk"] = {
                "stop_loss": {
                    "type": definition.risk.stop_loss_type,
                    "indicator": definition.risk.stop_indicator,
                    "multiplier": definition.risk.stop_multiplier,
                },
                "take_profit": {
                    "type": definition.risk.take_profit_type,
                    "indicator": definition.risk.take_profit_indicator,
                    "multiplier": definition.risk.take_profit_multiplier,
                },
            }

        if definition.sides:
            result["sides"] = {}
            visitor = SerializeGroupVisitor()
            for side, s in definition.sides.items():
                visitor.reset()
                visitor.visit_group(s.entry)
                side_obj: dict = {"entry": {"condition": visitor.result}}
                if s.exit is not None:
                    visitor.reset()
                    visitor.visit_group(s.exit)
                    side_obj["exit"] = {"condition": visitor.result}
                result["sides"][side] = side_obj

        if definition.metadata:
            result["metadata"] = definition.metadata

        return result


def _serialize_parameter(param) -> dict:
    p: dict = {"type": param.type, "default": param.default}
    if param.minimum is not None:
        p["minimum"] = param.minimum
    if param.maximum is not None:
        p["maximum"] = param.maximum
    return p
