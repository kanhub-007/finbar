"""Tests for YFinanceStockFetcher request construction."""

import pandas as pd

from finbar.infrastructure.services.yfinance_stock_fetcher import YFinanceStockFetcher


class StubRateLimiter:
    """No-op rate limiter for yfinance fetcher tests."""

    def wait(self) -> None:
        """Do not wait in tests."""


class StubTicker:
    """Captures yfinance history kwargs."""

    calls: list[dict] = []

    def __init__(self, symbol: str):
        self.symbol = symbol

    def history(self, **kwargs):
        StubTicker.calls.append(kwargs)
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
        )


def test_intraday_fetch_uses_requested_date_range(monkeypatch):
    StubTicker.calls.clear()
    monkeypatch.setattr(
        "finbar.infrastructure.services.yfinance_stock_fetcher.yf.Ticker",
        StubTicker,
    )
    fetcher = YFinanceStockFetcher(rate_limiter=StubRateLimiter())

    bars = fetcher.fetch(
        symbol="AAPL",
        interval="1h",
        start_date="2024-01-01",
        end_date="2024-01-03",
    )

    assert len(bars) == 1
    assert StubTicker.calls[0]["start"] == "2024-01-01"
    assert StubTicker.calls[0]["end"] == "2024-01-03"
    assert "period" not in StubTicker.calls[0]
