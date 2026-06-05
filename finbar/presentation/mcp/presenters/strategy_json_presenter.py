"""StrategyJsonPresenter — format strategy SDK MCP responses."""

from dataclasses import asdict


class StrategyJsonPresenter:
    """Convert strategy SDK use-case results into JSON-serializable dicts."""

    def validation_result(self, result) -> dict:
        """Format a strategy validation result."""
        return {
            "valid": result.valid,
            "schema_version": (
                result.definition.schema_version if result.definition else "2.0"
            ),
            "name": result.definition.name if result.definition else "",
            "required_indicators": result.required_indicators,
            "required_columns": result.required_columns,
            "primary_required_indicators": result.primary_required_indicators,
            "informative_required_indicators": (result.informative_required_indicators),
            "timeframe_intervals": result.timeframe_intervals,
            "missing_columns": result.missing_columns,
            "errors": [self.diagnostic(error) for error in result.errors],
            "warnings": [self.diagnostic(warning) for warning in result.warnings],
        }

    def backtest_result(self, result) -> dict:
        """Format a strategy JSON backtest result."""
        payload = {
            "valid": result.valid,
            "required_indicators": result.required_indicators,
            "primary_required_indicators": result.primary_required_indicators,
            "informative_required_indicators": (result.informative_required_indicators),
            "missing_columns": result.missing_columns,
            "errors": [self.diagnostic(error) for error in result.errors],
            "result": None,
        }
        if result.result is not None:
            payload["result"] = asdict(result.result)
        return payload

    def feature_result(self, result) -> dict:
        """Format a strategy feature computation result."""
        return {
            "bar_count": result.bar_count,
            "features_applied": result.features_applied,
            "bars": result.bars,
            "errors": [self.diagnostic(error) for error in result.errors],
            "error": result.error,
        }

    def diagnostic(self, error) -> dict:
        """Format a validation diagnostic."""
        return {"path": error.path, "message": error.message, "code": error.code}
