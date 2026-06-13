"""Edge case tests for HyperliquidFetcher caching and pagination."""

from datetime import UTC, datetime

import pytest

from finbar.core.domain.entities.price_bar import PriceBar
from finbar.infrastructure.services.hyperliquid_fetcher import (
    HyperliquidFetcher,
    _deduplicate_bars,
)


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


def _bar(timestamp: str, close: float) -> PriceBar:
    return PriceBar(
        symbol="BTC",
        source="hyperliquid",
        interval="1d",
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def test_deduplicate_bars_drops_duplicate_timestamps():
    """Regression: overlapping backward-paginated chunks can share a boundary
    bar. Duplicate timestamps would later be rejected by backtest validation."""
    bars = [
        _bar("2024-01-01", 100.0),
        _bar("2024-01-02", 101.0),
        _bar("2024-01-02", 101.0),  # duplicate of boundary bar
        _bar("2024-01-03", 102.0),
    ]
    result = _deduplicate_bars(bars)
    assert len(result) == 3
    assert [b.timestamp for b in result] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]


def test_max_history_deduplicates_boundary_bars(monkeypatch):
    """The merged history from backward pagination must pass through
    _deduplicate_bars so overlapping boundary bars are removed."""
    fetcher = HyperliquidFetcher(rate_limiter=StubRateLimiter())

    dedup_calls = []
    original_dedup = _deduplicate_bars

    def tracking_dedup(bars):
        dedup_calls.append(len(bars))
        return original_dedup(bars)

    # Make the first chunk return one bar, the second empty (genesis boundary).
    bar = _bar("2024-01-01", 100.0)
    responses = [[bar], []]

    def fake_fetch_chunk(symbol: str, interval: str, start_ms: int, end_ms: int):
        return responses.pop(0)

    fetcher._fetch_chunk = fake_fetch_chunk
    monkeypatch.setattr(
        "finbar.infrastructure.services.hyperliquid_fetcher._deduplicate_bars",
        tracking_dedup,
    )
    bars = fetcher._fetch_max_history("BTC", "1d")
    assert len(bars) == 1
    assert dedup_calls == [1]  # dedup was applied to the merged history
