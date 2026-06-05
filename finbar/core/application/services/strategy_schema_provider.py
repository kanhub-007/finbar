"""StrategySchemaProvider — canonical v2 strategy JSON schema."""


class StrategySchemaProvider:
    """Provide the canonical JSON Schema for v2 strategy definitions."""

    def get_schema(self) -> dict:
        """Return the v2 strategy definition JSON Schema."""
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://finbar.local/schemas/strategy-definition-v2.schema.json",
            "title": "Finbar Strategy Definition v2",
            "type": "object",
            "required": ["schema_version", "name", "sides"],
            "additionalProperties": True,
            "properties": {
                "schema_version": {"const": "2.0"},
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "parameters": {"type": "object"},
                "indicators": {"type": "array"},
                "sides": {"type": "object", "minProperties": 1},
                "metadata": {"type": "object"},
            },
            "$defs": {
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
                }
            },
        }
