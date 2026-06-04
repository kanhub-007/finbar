"""Composition root — wires all dependencies for API and MCP entry points.

Pattern copied from kapsula/startup/bootstrap.py.
The startup layer can import EVERYTHING — it's the composition root.
"""

import logging

from dotenv import load_dotenv

from finbar.infrastructure.data.connection import init_db
from finbar.infrastructure.logging_config import setup_logging

load_dotenv()


def bootstrap(log_level: str = "INFO") -> None:
    """Initialize database and logging. Call once at startup."""
    setup_logging(log_level=log_level)
    logger = logging.getLogger(__name__)
    init_db()
    logger.info("Database tables initialized")
