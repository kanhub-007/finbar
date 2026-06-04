"""MCP job tools — progress, results, cancel."""

from fastmcp import FastMCP

from ._shared import _get_job_manager


def register_job_tools(mcp: FastMCP) -> None:
    """Register job management MCP tools."""

    @mcp.tool(
        name="get_job_progress",
        description=(
            "Check the status of a background fetch job. "
            "Returns status (queued/running/completed/failed/cancelled) "
            "and progress percentage."
        ),
    )
    def get_job_progress(job_id: str) -> str:
        manager = _get_job_manager()
        job = manager.get(job_id)
        if job is None:
            return f"Job not found: {job_id}"
        return (
            f"Job: {job.job_id}\n"
            f"Symbol: {job.symbol} ({job.source}, {job.interval})\n"
            f"Status: {job.status}\n"
            f"Progress: {job.progress_pct}%\n"
            + (f"Error: {job.error}" if job.error else "")
        )

    @mcp.tool(
        name="get_job_results",
        description=(
            "Retrieve the results of a completed background fetch job. "
            "Returns the fetched OHLCV bars as JSON. "
            "Only works after status='completed'."
        ),
    )
    def get_job_results(job_id: str) -> str:
        manager = _get_job_manager()
        job = manager.get(job_id)
        if job is None:
            return f"Job not found: {job_id}"
        if job.status != "completed":
            return (
                f"Job {job_id} is not complete (status: {job.status}). "
                f"Use get_job_progress('{job_id}') to check."
            )
        return job.result or "No results"

    @mcp.tool(
        name="cancel_job",
        description="Cancel a running or queued background fetch job.",
    )
    def cancel_job(job_id: str) -> str:
        manager = _get_job_manager()
        job = manager.cancel(job_id)
        if job is None:
            return f"Job not found: {job_id}"
        return f"Job {job_id} cancelled (was {job.symbol})"
