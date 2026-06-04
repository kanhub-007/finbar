"""Composition root — wires all dependencies for API and MCP entry points.

The startup layer can import EVERYTHING — it's the composition root.
"""

import logging

from dotenv import load_dotenv

# Import table modules so Base.metadata knows about them before create_all()
import finbar.infrastructure.tables.price_bar  # noqa: F401
import finbar.infrastructure.tables.strategy_definition  # noqa: F401
import finbar.infrastructure.tables.symbol_info  # noqa: F401
from finbar.infrastructure.data.connection import init_db as _init_db
from finbar.infrastructure.logging_config import setup_logging

load_dotenv()


def bootstrap(log_level: str = "INFO") -> None:
    """Initialize database and logging. Call once at startup."""
    setup_logging(log_level=log_level)
    logger = logging.getLogger(__name__)
    _init_db()
    logger.info("Database tables initialized")
