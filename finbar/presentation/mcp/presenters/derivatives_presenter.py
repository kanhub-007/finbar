"""DerivativesPresenter — format derivatives metrics results for MCP."""

from dataclasses import asdict

from finbar.core.application.dto.fetch_derivatives_result import (
    FetchDerivativesResult,
)


class DerivativesPresenter:
    """Convert derivatives fetch results to JSON‑serializable dicts."""

    def fetch_result(self, result: FetchDerivativesResult) -> dict:
        """Format a derivatives fetch result for MCP response."""
        payload = asdict(result)
        return payload
