"""Shared helper for API routes that need a DB session."""

from finbar.startup.service_factory import _get_db


def _get_db_for_metrics():
    """Return a DB session for metric capability checks."""
    return _get_db()
