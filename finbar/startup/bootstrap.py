"""Composition root — wires all dependencies for API and MCP entry points.

Pattern copied from kapsula/startup/bootstrap.py.
The startup layer can import EVERYTHING — it's the composition root.
"""

import logging

from dotenv import load_dotenv

from finbar.infrastructure.data.connection import init_db

load_dotenv()
logger = logging.getLogger(__name__)


def bootstrap() -> None:
    """Initialize database. Call once at startup."""
    init_db()
    logger.info("Database tables initialized")
