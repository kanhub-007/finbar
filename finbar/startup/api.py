"""REST API startup — composition root for the FastAPI server."""

from fastapi import FastAPI

from finbar.startup.bootstrap import bootstrap


def create_app() -> FastAPI:
    """Build the FastAPI application with all routes registered.

    Returns:
        Configured FastAPI app instance ready to serve.
    """
    bootstrap()

    app = FastAPI(
        title="Finbar",
        description=(
            "Multi-source financial OHLCV bars — yfinance, Hyperliquid, "
            "and more. Cache-enabled with background fetch jobs."
        ),
        version="0.1.0",
    )

    from finbar.presentation.api.routes.analysis import router as analysis_router
    from finbar.presentation.api.routes.enrichment import router as enrichment_router
    from finbar.presentation.api.routes.health import router as health_router
    from finbar.presentation.api.routes.jobs import router as jobs_router
    from finbar.presentation.api.routes.optimization import (
        router as optimization_router,
    )
    from finbar.presentation.api.routes.prices import router as prices_router
    from finbar.presentation.api.routes.strategy_json import router as strategy_router
    from finbar.presentation.api.routes.symbols import router as symbols_router

    app.include_router(strategy_router)
    app.include_router(symbols_router)
    app.include_router(prices_router)
    app.include_router(analysis_router)
    app.include_router(jobs_router)
    app.include_router(enrichment_router)
    app.include_router(optimization_router)
    app.include_router(health_router)

    return app
