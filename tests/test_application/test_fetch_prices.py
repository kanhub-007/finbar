"""Unit tests for fetch and cache use cases with mocked interfaces."""

from finbar.core.application.dto.fetch_prices_request import FetchPricesRequest
from finbar.core.application.dto.fetch_prices_result import FetchPricesResult
from finbar.core.application.use_cases.fetch_prices import FetchPricesUseCase
from finbar.core.domain.entities.price_bar import PriceBar


class StubFetcher:
    """Returns fixed price bars."""

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_date: str | None,
        end_date: str | None,
    ):
        return [
            PriceBar(
                symbol=symbol,
                source="test",
                interval=interval,
                timestamp="2024-01-01",
                open=100.0,
                high=105.0,
                low=98.0,
                close=102.0,
                volume=1000000,
            ),
            PriceBar(
                symbol=symbol,
                source="test",
                interval=interval,
                timestamp="2024-01-02",
                open=102.0,
                high=107.0,
                low=100.0,
                close=104.0,
                volume=1100000,
            ),
        ]


class StubEmptyFetcher:
    def fetch(self, **kwargs):
        return []


class StubCache:
    def __init__(self):
        self.saved_bars = []

    def save_bars(self, bars):
        self.saved_bars.extend(bars)
        return len(bars)


class TestFetchPricesUseCase:
    def test_successful_fetch(self):
        uc = FetchPricesUseCase(StubFetcher(), StubCache())
        result = uc.execute(
            FetchPricesRequest(
                symbol="AAPL",
                source="test",
                interval="1d",
            )
        )
        assert isinstance(result, FetchPricesResult)
        assert result.bar_count == 2
        assert result.symbol == "AAPL"
        assert result.origin == "fresh"
        assert result.error is None

    def test_empty_fetch_returns_error(self):
        uc = FetchPricesUseCase(StubEmptyFetcher(), StubCache())
        result = uc.execute(
            FetchPricesRequest(
                symbol="NODATA",
                source="test",
                interval="1d",
            )
        )
        assert result.bar_count == 0
        assert result.error is not None

    def test_bars_saved_to_cache(self):
        cache = StubCache()
        uc = FetchPricesUseCase(StubFetcher(), cache)
        uc.execute(
            FetchPricesRequest(
                symbol="AAPL",
                source="test",
                interval="1d",
            )
        )
        assert len(cache.saved_bars) == 2
