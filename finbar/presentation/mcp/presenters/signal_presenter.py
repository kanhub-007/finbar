"""SignalPresenter — format signal computation results for MCP."""

from dataclasses import asdict

from finbar.core.application.dto.compute_signals_result import ComputeSignalsResult


class SignalPresenter:
    """Convert signal computation results to JSON‑serializable dicts."""

    @staticmethod
    def compute_result(result: ComputeSignalsResult) -> dict:
        """Format a signal computation result for MCP response."""
        return asdict(result)
