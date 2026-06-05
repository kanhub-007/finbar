"""Deprecated bar conversion compatibility helpers.

Application use cases now depend on the BarFrameConverter domain interface so
pandas-specific conversion lives in infrastructure.
"""


def bars_to_dataframe(bars: list[dict]) -> list[dict]:
    """Return a shallow copy of bars for backward-compatible callers."""
    return list(bars)


def dataframe_to_bars(df: list[dict]) -> list[dict]:
    """Return a shallow copy of bars for backward-compatible callers."""
    return list(df)
