"""SymbolInfo domain entity — company/asset metadata.

and yfinance's yf.Ticker(symbol).info dict.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolInfo:
    """Company or asset metadata for a ticker symbol.

    Immutable value object. Fields are a subset of what yfinance
    returns from Ticker.info for stocks, plus fields applicable
    to crypto assets (Hyperliquid, etc.).
    """

    symbol: str
    company_name: str = ""
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
    fetched_at: str = ""
