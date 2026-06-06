"""DerivativesPresenter — format derivatives metrics results for MCP."""

from dataclasses import asdict

from finbar.core.application.dto.fetch_derivatives_result import (
    FetchDerivativesResult,
)


class DerivativesPresenter:
    """Convert derivatives fetch results to JSON‑serializable dicts."""

    @staticmethod
    def fetch_result(result: FetchDerivativesResult) -> dict:
        """Format a derivatives fetch result for MCP response."""
        payload = asdict(result)
        # Convert metrics list to list of dicts with default=str for None
        payload["metrics"] = []
        for m in result.metrics:
            d = asdict(m)
            # Replace None with null in JSON (default behaviour)
            payload["metrics"].append(d)
        return payload
