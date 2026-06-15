"""YFinance stock data fetcher — implements StockDataFetcher.

Fetches historical OHLCV candles from Yahoo Finance via the yfinance library.
Supports multiple intervals (5min through 1wk) with rate limiting.

Implements the StockDataFetcher interface (Strategy pattern).
"""

import logging

import pandas as pd
import yfinance as yf

from finbar.core.domain.entities.price_bar import PriceBar
from finbar.core.domain.entities.symbol_info import SymbolInfo
from finbar.core.domain.interfaces.stock_data_fetcher import StockDataFetcher
from finbar.infrastructure.services.bar_validator import validate_bar
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter

logger = logging.getLogger(__name__)

# ── Interval / period mappings ────────────────────────────

INTERVAL_MAP: dict[str, str] = {
    "5min": "5m",
    "30min": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
}

PERIOD_MAP: dict[str, str] = {
    "5min": "60d",
    "30min": "60d",
    "1h": "730d",
    "1d": "max",
    "1w": "max",
}


class YFinanceStockFetcher(StockDataFetcher):
    """Fetches OHLCV price bars and symbol metadata from Yahoo Finance."""

    def __init__(self, rate_limiter: YahooFinanceRateLimiter | None = None):
        self._rate_limiter = rate_limiter or YahooFinanceRateLimiter()

    # ── StockDataFetcher implementation ──────────────────────────────────

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[PriceBar]:
        """Fetch raw OHLCV price bars.

        Args:
            symbol: Ticker symbol (e.g., 'AAPL').
            interval: Time interval ('5min', '30min', '1h', '1d', '1w').
            start_date: Optional start date (ISO format).
            end_date: Optional end date (ISO format).

        Returns:
            List of PriceBar domain entities. Empty list if no data or error.
        """
        yf_interval = INTERVAL_MAP.get(interval, interval)
        period = PERIOD_MAP.get(interval, "60d")

        try:
            self._rate_limiter.wait()

            ticker = yf.Ticker(symbol)

            history_kwargs = {
                "interval": yf_interval,
                "auto_adjust": False,
                "actions": False,
            }
            if start_date or end_date:
                if start_date:
                    history_kwargs["start"] = start_date
                if end_date:
                    history_kwargs["end"] = end_date
            else:
                history_kwargs["period"] = period

            df = ticker.history(**history_kwargs)

            if df.empty:
                logger.debug("Empty response for %s (%s)", symbol, interval)
                return []

            return self._parse_dataframe(df, symbol, interval, "yfinance")

        except Exception:
            logger.exception("Error fetching %s (%s) from yfinance", symbol, interval)
            return []

    def fetch_latest(self, symbol: str) -> PriceBar | None:
        """Fetch the most recent OHLCV bar."""
        bars = self.fetch(symbol, "1d")
        return bars[-1] if bars else None

    def fetch_info(self, symbol: str) -> SymbolInfo | None:
        """Fetch company/asset metadata from yfinance."""
        try:
            self._rate_limiter.wait()
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or info.get("symbol") is None:
                return None

            return SymbolInfo(
                symbol=symbol.upper(),
                company_name=str(info.get("longName", info.get("shortName", ""))),
                sector=info.get("sector"),
                industry=info.get("industry"),
                exchange=info.get("exchange"),
                market_cap=info.get("marketCap"),
                fetched_at=pd.Timestamp.now(tz="UTC").isoformat(),
            )
        except Exception:
            logger.exception("Error fetching info for %s", symbol)
            return None

    # ── DataFrame parsing ─────────────────

    def _parse_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        source: str,
    ) -> list[PriceBar]:
        """Parse yfinance DataFrame into PriceBar domain entities.

        (_parse_yahoo_df function).
        """
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Guard against missing required columns
        required_columns = ["open", "high", "low", "close"]
        if not all(col in df.columns for col in required_columns):
            logger.warning(
                "Missing required columns in yfinance response. " "Columns: %s",
                df.columns.tolist(),
            )
            return []

        # Find the timestamp column
        timestamp_col = None
        for col in ["datetime", "date"]:
            if col in df.columns:
                timestamp_col = col
                break

        if timestamp_col is None:
            logger.warning("No timestamp column in yfinance response")
            return []

        # Convert to UTC timestamps
        timestamps = pd.to_datetime(df[timestamp_col])
        if timestamps.dt.tz is not None:
            timestamps = timestamps.dt.tz_convert("UTC")
        timestamp_utc = timestamps.dt.strftime("%Y-%m-%dT%H:%M:%S.%f")

        # Vectorised extraction: pull all columns into numpy arrays ONCE and
        # iterate by index, instead of df.iterrows() which allocates a
        # pd.Series (and boxes every value) per row.
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        has_volume = "volume" in df.columns
        volumes = df["volume"].to_numpy() if has_volume else None
        ts_arr = timestamp_utc.to_numpy()
        symbol_upper = symbol.upper()

        bars: list[PriceBar] = []
        for i in range(len(df)):
            o = float(opens[i])
            h = float(highs[i])
            lo = float(lows[i])
            c = float(closes[i])
            raw_v = volumes[i] if has_volume else None
            v = int(raw_v) if pd.notna(raw_v) else None
            ts = str(ts_arr[i])

            # Validate bar
            if not validate_bar(symbol, ts, o, h, lo, c, v):
                continue

            bars.append(
                PriceBar(
                    symbol=symbol_upper,
                    source=source,
                    interval=interval,
                    timestamp=ts,
                    open=o,
                    high=h,
                    low=lo,
                    close=c,
                    volume=v,
                )
            )

        return bars
