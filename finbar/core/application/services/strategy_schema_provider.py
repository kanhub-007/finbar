"""StrategySchemaProvider — canonical strategy JSON schema."""


class StrategySchemaProvider:
    """Provide the canonical JSON Schema for strategy definitions."""

    def get_schema(self) -> dict:
        """Return the strategy definition JSON Schema."""
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://finbar.local/schemas/strategy-definition.schema.json",
            "title": "Finbar Strategy Definition",
            "type": "object",
            "required": ["schema_version", "name", "sides"],
            "additionalProperties": True,
            "properties": {
                "schema_version": {"const": "2.0"},
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "parameters": {"type": "object"},
                "timeframes": {"$ref": "#/$defs/timeframes"},
                "indicators": {"type": "array"},
                "features": {"type": "array"},
                "risk": {"type": "object"},
                "sides": {"type": "object", "minProperties": 1},
                "metadata": {"type": "object"},
            },
            "$defs": {
                "timeframes": {
                    "type": "object",
                    "required": ["primary"],
                    "properties": {
                        "primary": {"type": "string"},
                        "informative": {
                            "type": "array",
                            "maxItems": 3,
                            "items": {
                                "type": "object",
                                "required": ["alias", "interval"],
                                "properties": {
                                    "alias": {"type": "string", "minLength": 1},
                                    "interval": {"type": "string", "minLength": 1},
                                },
                            },
                        },
                    },
                },
                "operators": {
                    "enum": [
                        "<",
                        ">",
                        "<=",
                        ">=",
                        "==",
                        "!=",
                        "crosses_above",
                        "crosses_below",
                        "between",
                        "not_between",
                        "is_true",
                        "is_false",
                        "exists",
                        "missing",
                    ]
                },
            },
        }
