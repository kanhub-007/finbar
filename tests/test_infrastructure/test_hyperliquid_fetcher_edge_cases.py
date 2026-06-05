"""Edge case tests for HyperliquidFetcher caching and pagination."""

from datetime import UTC, datetime

import pytest

from finbar.core.domain.entities.price_bar import PriceBar
from finbar.infrastructure.services.hyperliquid_fetcher import HyperliquidFetcher


class StubRateLimiter:
    """No-op rate limiter for HyperliquidFetcher tests."""

    def wait(self, weight: int = 1) -> None:
        """Do not wait in tests."""

    def on_success(self) -> None:
        """Record no-op success."""

    def on_rate_limit_error(self) -> None:
        """Record no-op rate-limit failure."""


def test_hip3_cache_refreshes_after_spot_cache_warmup():
    fetcher = HyperliquidFetcher(rate_limiter=StubRateLimiter())
    calls: list[bool] = []

    def fake_fetch_all_tickers(include_hip3: bool = False):
        calls.append(include_hip3)
        hip3 = [{"symbol": "flx:TSLA"}] if include_hip3 else []
        return [{"symbol": "BTC"}], [{"symbol": "ETH"}], hip3

    fetcher._fetch_all_tickers = fake_fetch_all_tickers

    assert fetcher.fetch_spot_tickers() == [{"symbol": "BTC"}]
    assert fetcher.fetch_hip3_tickers() == [{"symbol": "flx:TSLA"}]
    assert calls == [False, True]


def test_max_history_raises_when_chunk_fetch_fails():
    fetcher = HyperliquidFetcher(rate_limiter=StubRateLimiter())
    bar = PriceBar(
        symbol="BTC",
        source="hyperliquid",
        interval="1d",
        timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"),
        open=1.0,
        high=2.0,
        low=1.0,
        close=1.5,
        volume=1,
    )
    responses = [[bar], None]

    def fake_fetch_chunk(symbol: str, interval: str, start_ms: int, end_ms: int):
        return responses.pop(0)

    fetcher._fetch_chunk = fake_fetch_chunk

    with pytest.raises(RuntimeError, match="Failed to fetch BTC chunk"):
        fetcher._fetch_max_history("BTC", "1d")
