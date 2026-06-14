"""DataClass — the data class required to compute a market metric."""

from enum import Enum


class DataClass(str, Enum):
    """Known data classes that Finbar can source or reference."""

    DAILY_OHLCV = "daily_ohlcv"
    INTRADAY_OHLCV = "intraday_ohlcv"
    TRADES = "trades"
    QUOTES = "quotes"
    TRADES_AND_QUOTES = "trades_and_quotes"
    LEVEL_2_ORDER_BOOK = "level_2_order_book"
    ORDER_BOOK_EVENTS = "order_book_events"
    EXTERNAL_PROVIDER = "external_provider"
