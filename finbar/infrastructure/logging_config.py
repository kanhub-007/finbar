"""Application-wide logging configuration.
Configures console (INFO+) and file (DEBUG) handlers.
"""

import logging
import sys

from finbar.config.settings import DATA_DIR

LOGS_DIR = DATA_DIR / "logs"


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure root logger with console and file handlers.

    Args:
        log_level: Console log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Configured root logger.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — DEBUG level, everything goes to file
    file_handler = logging.FileHandler(LOGS_DIR / "finbar.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler — INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()  # Prevent duplicate handlers on reload
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)

    return root_logger
