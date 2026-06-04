"""FetchPricesRequest DTO — input for the fetch prices use case.

Data crossing the application boundary uses this dedicated DTO.
Designed from API params in h_stocks/api/routers/stocks_prices.py.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchPricesRequest:
    """Request to fetch OHLCV prices from a data source.

    All fields are required for a fetch operation. The source
    determines which StockDataFetcher implementation is used.
    """

    symbol: str
    source: str
    interval: str
    start_date: str | None = None
    end_date: str | None = None
