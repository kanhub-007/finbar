"""Composition root — wires all dependencies for API and MCP entry points.

The startup layer can import EVERYTHING — it's the composition root.
"""

import logging

from dotenv import load_dotenv
from sqlalchemy import text as sa_text

# Import table modules so Base.metadata knows about them before create_all()
import finbar.infrastructure.tables.backtest_result  # noqa: F401
import finbar.infrastructure.tables.coinglass_data  # noqa: F401
import finbar.infrastructure.tables.indicator_artifact  # noqa: F401
import finbar.infrastructure.tables.price_bar  # noqa: F401
import finbar.infrastructure.tables.strategy_document  # noqa: F401
import finbar.infrastructure.tables.symbol_info  # noqa: F401
from finbar.infrastructure.data.connection import init_db as _init_db
from finbar.infrastructure.logging_config import setup_logging

load_dotenv()


def bootstrap(log_level: str = "INFO") -> None:
    """Initialize database and logging. Call once at startup."""
    setup_logging(log_level=log_level)
    logger = logging.getLogger(__name__)
    _init_db()
    _migrate_db()
    logger.info("Database tables initialized")


def _migrate_db() -> None:
    """Add new columns for existing databases without migrations framework."""
    from finbar.infrastructure.data.connection import engine

    for table, column_def in [
        ("indicator_artifacts", "content_hash TEXT DEFAULT ''"),
        ("backtest_results", "created_at TEXT DEFAULT ''"),
    ]:
        try:
            with engine.connect() as conn:
                conn.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))
                conn.commit()
        except Exception:
            pass  # Column already exists
