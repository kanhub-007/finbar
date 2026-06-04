"""Hyperliquid stock data fetcher — implements StockDataFetcher.

(HyperliquidFetcher class) and the chunk config from

Supports three market types:
- SPOT: plain ticker, e.g. "PURR", "BTC"
- PERP: plain ticker, e.g. "BTC", "ETH"
- HIP-3: dex:COIN format, e.g. "flx:TSLA" (lowercase dex, uppercase coin)

Implements StockDataFetcher (Strategy pattern).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from hyperliquid.info import Info
from hyperliquid.utils import constants

from finbar.core.domain.entities.price_bar import PriceBar
from finbar.core.domain.entities.symbol_info import SymbolInfo
from finbar.core.domain.interfaces.stock_data_fetcher import StockDataFetcher
from finbar.infrastructure.services.bar_validator import validate_bar
from finbar.infrastructure.services.hyperliquid_rate_limiter import (
    TICKER_WEIGHT,
    HyperliquidRateLimiter,
    calculate_candle_weight,
)

logger = logging.getLogger(__name__)

# ── Interval mapping ──────────────────────────────────────────────────────

INTERVAL_MAP: dict[str, str] = {
    "5min": "5m",
    "30min": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1w",
}

# Max bars per request per interval
MAX_BARS: dict[str, int] = {
    "5min": 5000,
    "30min": 5000,
    "1h": 5000,
    "1d": 5000,
    "1w": 5000,
}

# API limit per interval in days (approximate)
API_LIMIT_DAYS: dict[str, int] = {
    "5min": 17,
    "30min": 90,
    "1h": 208,
    "1d": 1095,  # ~3 years
    "1w": 1095,
}

# Interval duration in milliseconds
INTERVAL_MS: dict[str, int] = {
    "5min": 5 * 60 * 1000,
    "30min": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
}


class HyperliquidFetcher(StockDataFetcher):
    """Fetches OHLCV price bars and ticker metadata from Hyperliquid.

    Handles spot, perpetual, and HIP-3 markets. Rate-limited via
    token bucket. Ticker metadata is cached for 5 minutes.
    """

    # Class-level perp_dexs cache (shared across instances)
    _perp_dexs_cache: list[dict] | None = None
    _perp_dexs_cache_time: float = 0.0
    _PERP_DEXS_TTL: float = 300.0  # 5 minutes

    def __init__(
        self,
        testnet: bool = False,
        rate_limiter: HyperliquidRateLimiter | None = None,
    ):
        url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self._rate_limiter = rate_limiter or HyperliquidRateLimiter()
        self._url = url

        # Ticker cache
        self._ticker_cache: dict[str, list[dict]] = {}
        self._cache_time: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes

        # Lazy init — Info client needs perp_dexs which needs rate-limited API call
        self._info: Info | None = None

    def _get_info(self) -> Info:
        """Lazy-init the Hyperliquid Info client with perp_dexs."""
        if self._info is not None:
            return self._info

        current_time = time.time()
        if (
            HyperliquidFetcher._perp_dexs_cache is not None
            and (current_time - HyperliquidFetcher._perp_dexs_cache_time)
            < HyperliquidFetcher._PERP_DEXS_TTL
        ):
            dex_names = [
                d.get("name", "") if d else ""
                for d in HyperliquidFetcher._perp_dexs_cache
            ]
        else:
            self._rate_limiter.wait(weight=10)
            temp_info = Info(self._url, skip_ws=True)
            perp_dexs = temp_info.perp_dexs()
            HyperliquidFetcher._perp_dexs_cache = perp_dexs
            HyperliquidFetcher._perp_dexs_cache_time = current_time
            dex_names = [d.get("name", "") if d else "" for d in perp_dexs]
            logger.debug("Fetched perp_dexs: %d DEXs", len(dex_names))

        self._info = Info(self._url, skip_ws=True, perp_dexs=dex_names)
        return self._info

    # ── StockDataFetcher implementation ──────────────────────────────────

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[PriceBar]:
        """Fetch OHLCV price bars from Hyperliquid.

        If no date range is given, fetches max history (now → backwards
        until empty, aka genesis boundary).

        Args:
            symbol: Ticker symbol. For HIP-3 use "dex:COIN" format.
            interval: Time interval.
            start_date: Optional start date (ISO format).
            end_date: Optional end date (ISO format).

        Returns:
            List of PriceBar domain entities.
        """
        try:
            if start_date and end_date:
                return self._fetch_date_range(symbol, interval, start_date, end_date)
            return self._fetch_max_history(symbol, interval)
        except Exception:
            logger.exception(
                "Error fetching %s (%s) from hyperliquid", symbol, interval
            )
            return []

    def fetch_latest(self, symbol: str) -> PriceBar | None:
        """Fetch the most recent OHLCV bar."""
        bars = self._fetch_date_range(
            symbol,
            "1d",
            (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            datetime.now(UTC).isoformat(),
        )
        return bars[-1] if bars else None

    def fetch_info(self, symbol: str) -> SymbolInfo | None:
        """Fetch asset metadata from ticker cache."""
        tickers = self._get_cached_tickers()
        all_tickers = tickers.get("spot", []) + tickers.get("perp", [])
        for t in all_tickers:
            if t.get("symbol", "").upper() == symbol.upper():
                return SymbolInfo(
                    symbol=symbol.upper(),
                    company_name=t.get("name", symbol),
                )
        return None

    # ── Fetch strategies ──────────────────────────────────────────────────

    def _fetch_max_history(self, symbol: str, interval: str) -> list[PriceBar]:
        """Fetch full history from now backwards until no more data.

        pattern: temporal chunks going backwards, stop on empty chunk.
        """
        max_bars = MAX_BARS.get(interval, 1000)
        interval_ms = INTERVAL_MS.get(interval, 60 * 60 * 1000)
        chunk_ms = interval_ms * max_bars

        now = datetime.now(UTC)
        all_bars: list[PriceBar] = []
        chunk_end_ms = int(now.timestamp() * 1000)

        max_chunks = 200  # Safety limit

        for _ in range(max_chunks):
            chunk_start_ms = chunk_end_ms - chunk_ms

            bars = self._fetch_chunk(symbol, interval, chunk_start_ms, chunk_end_ms)

            if not bars:
                logger.debug(
                    "Empty chunk for %s at %s — genesis boundary",
                    symbol,
                    datetime.fromtimestamp(chunk_start_ms / 1000, tz=UTC).isoformat(),
                )
                break

            all_bars = bars + all_bars  # Prepend to maintain chronological
            chunk_end_ms = chunk_start_ms

        logger.info(
            "Fetched %d bars for %s (%s) — full history",
            len(all_bars),
            symbol,
            interval,
        )
        return all_bars

    def _fetch_date_range(
        self, symbol: str, interval: str, start_date: str, end_date: str
    ) -> list[PriceBar]:
        """Fetch bars for a specific date range, paginated into chunks."""
        max_bars = MAX_BARS.get(interval, 1000)
        interval_ms = INTERVAL_MS.get(interval, 60 * 60 * 1000)
        chunk_ms = interval_ms * max_bars

        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        all_bars: list[PriceBar] = []
        current_start = start_ms

        while current_start < end_ms:
            current_end = min(current_start + chunk_ms, end_ms)
            bars = self._fetch_chunk(symbol, interval, current_start, current_end)
            all_bars.extend(bars)
            current_start = current_end
            time.sleep(0.05)  # Small delay between chunks

            if len(all_bars) > 50000:  # Safety limit
                logger.warning("%s: hit safety limit of 50000 bars", symbol)
                break

        return all_bars

    def _fetch_chunk(
        self, symbol: str, interval: str, start_ms: int, end_ms: int
    ) -> list[PriceBar]:
        """Fetch a single temporal chunk with rate limiting.

        Detects market type from symbol format:
        - "dex:COIN" → HIP-3 (custom POST)
        - plain → spot/perp (candles_snapshot)
        """
        api_interval = INTERVAL_MAP.get(interval, "1h")
        estimated_bars = min(
            abs(end_ms - start_ms) // INTERVAL_MS.get(interval, 3600000),
            5000,
        )
        weight = calculate_candle_weight(estimated_bars)

        self._rate_limiter.wait(weight=weight)

        try:
            if ":" in symbol:
                candles = self._fetch_hip3_chunk(symbol, api_interval, start_ms, end_ms)
            else:
                info = self._get_info()
                candles = info.candles_snapshot(symbol, api_interval, start_ms, end_ms)

            self._rate_limiter.on_success()
            return self._process_candles(candles, symbol, interval)

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate limit" in error_str.lower():
                self._rate_limiter.on_rate_limit_error()
                logger.warning("Rate limit on %s chunk", symbol)
            else:
                logger.error("Error fetching %s chunk: %s", symbol, e)
            return []

    def _fetch_hip3_chunk(
        self, symbol: str, api_interval: str, start_ms: int, end_ms: int
    ) -> list[dict]:
        """Fetch candles for a HIP-3 ticker via custom POST /info.

        HIP-3 symbols are formatted as "dex:COIN". The dex name must be
        lowercase and the coin must be uppercase for the API.
        """
        parts = symbol.split(":")
        dex_name = parts[0].lower()
        coin = parts[1].upper()
        api_symbol = f"{dex_name}:{coin}"

        info = self._get_info()
        result = info.post(
            "/info",
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": api_symbol,
                    "interval": api_interval,
                    "startTime": start_ms,
                    "endTime": end_ms,
                },
            },
        )
        return result if isinstance(result, list) else []

    # ── Candle processing ─────────────────────────

    def _process_candles(
        self,
        candles: list[dict],
        symbol: str,
        interval: str,
    ) -> list[PriceBar]:
        """Convert Hyperliquid API response to PriceBar entities."""
        if not candles:
            return []

        bars: list[PriceBar] = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue

            try:
                ts_ms = candle.get("t")
                if not ts_ms:
                    continue

                ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime(
                    "%Y-%m-%d %H:%M:%S.%f"
                )

                o = float(candle.get("o", 0))
                h = float(candle.get("h", 0))
                lo = float(candle.get("l", 0))
                c = float(candle.get("c", 0))
                v_raw = candle.get("v")
                v = int(float(v_raw)) if v_raw is not None else None

                if not validate_bar(symbol, ts, o, h, lo, c, v):
                    continue

                bars.append(
                    PriceBar(
                        symbol=symbol,
                        source="hyperliquid",
                        interval=interval,
                        timestamp=ts,
                        open=o,
                        high=h,
                        low=lo,
                        close=c,
                        volume=v,
                    )
                )
            except (ValueError, TypeError, KeyError) as e:
                logger.warning("Failed to parse candle: %s — %s", candle, e)
                continue

        return bars

    # ── Ticker discovery ──────────────────────────────────────────────────

    def fetch_spot_tickers(self) -> list[dict]:
        """Fetch all spot market tickers."""
        tickers = self._get_cached_tickers()
        return tickers.get("spot", [])

    def fetch_perp_tickers(self) -> list[dict]:
        """Fetch all perpetual futures tickers."""
        tickers = self._get_cached_tickers()
        return tickers.get("perp", [])

    def fetch_hip3_tickers(self) -> list[dict]:
        """Fetch all HIP-3 (third-party DEX) tickers."""
        tickers = self._get_cached_tickers(include_hip3=True)
        return tickers.get("hip3", [])

    def _get_cached_tickers(self, include_hip3: bool = False) -> dict[str, list[dict]]:
        """Return cached ticker lists, refreshing if TTL expired."""
        current_time = time.time()
        if (current_time - self._cache_time) < self._cache_ttl and self._ticker_cache:
            return self._ticker_cache

        spot, perp, hip3 = self._fetch_all_tickers(include_hip3=include_hip3)
        self._ticker_cache = {"spot": spot, "perp": perp, "hip3": hip3}
        self._cache_time = current_time
        return self._ticker_cache

    def _fetch_all_tickers(
        self, include_hip3: bool = False
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """Fetch all tickers from Hyperliquid API."""
        self._rate_limiter.wait(weight=TICKER_WEIGHT)

        try:
            info = self._get_info()
            spot_meta = info.spot_meta_and_asset_ctxs()
            perp_meta = info.meta_and_asset_ctxs()

            spot_tickers = self._process_spot_tickers(spot_meta)
            perp_tickers = self._process_perp_tickers(perp_meta)

            hip3_tickers: list[dict] = []
            if include_hip3:
                hip3_tickers = self._fetch_hip3_tickers_list()

            return spot_tickers, perp_tickers, hip3_tickers
        except Exception:
            logger.exception("Error fetching hyperliquid tickers")
            return [], [], []

    def _process_spot_tickers(self, spot_data: tuple) -> list[dict]:
        """Parse spot_meta_and_asset_ctxs response."""
        if not spot_data or len(spot_data) < 2:
            return []

        meta, asset_ctxs = spot_data
        universe = meta.get("universe", [])
        if not universe:
            return []

        asset_contexts = asset_ctxs[0] if isinstance(asset_ctxs[0], list) else []
        tokens = meta.get("tokens", [])

        tickers: list[dict] = []
        for i, item in enumerate(universe):
            token_indices = item.get("tokens", [])
            if len(token_indices) < 2:
                continue

            base_token = None
            for token in tokens:
                if token.get("index") == token_indices[0]:
                    base_token = token
                    break

            symbol = item.get("name", "")
            base_symbol = symbol.split("/")[0] if "/" in symbol else symbol
            ctx = asset_contexts[i] if i < len(asset_contexts) else {}

            tickers.append(
                {
                    "symbol": base_symbol,
                    "name": (base_token.get("name") if base_token else base_symbol),
                    "is_perpetual": False,
                    "is_hip3": False,
                    "mark_price": _safe_float(ctx.get("midPx")),
                    "day_volume": _safe_float(ctx.get("dayNtlVlm")),
                }
            )

        return tickers

    def _process_perp_tickers(self, perp_data: tuple) -> list[dict]:
        """Parse meta_and_asset_ctxs response for perps."""
        if not perp_data or len(perp_data) < 2:
            return []

        meta, asset_ctxs = perp_data
        universe = meta.get("universe", [])
        if not universe:
            return []

        asset_contexts = asset_ctxs[0] if isinstance(asset_ctxs[0], list) else []

        tickers: list[dict] = []
        for i, item in enumerate(universe):
            symbol = item.get("name", "")
            if not symbol:
                continue
            ctx = asset_contexts[i] if i < len(asset_contexts) else {}

            tickers.append(
                {
                    "symbol": symbol,
                    "name": symbol,
                    "is_perpetual": True,
                    "is_hip3": False,
                    "max_leverage": item.get("maxLeverage"),
                    "mark_price": _safe_float(ctx.get("markPx")),
                    "funding_rate": _safe_float(ctx.get("funding")),
                    "open_interest": _safe_float(ctx.get("openInterest")),
                    "day_volume": _safe_float(ctx.get("dayNtlVlm")),
                }
            )

        return tickers

    def _fetch_hip3_tickers_list(self) -> list[dict]:
        """Fetch HIP-3 tickers from all third-party DEXs."""
        all_hip3: list[dict] = []

        try:
            info = self._get_info()
            perp_dexs = info.perp_dexs()

            for dex in perp_dexs[1:]:  # Skip null (main DEX)
                dex_name = dex.get("name", "")
                if not dex_name:
                    continue

                self._rate_limiter.wait(weight=TICKER_WEIGHT)

                try:
                    meta_and_ctxs = info.post(
                        "/info",
                        {"type": "metaAndAssetCtxs", "dex": dex_name},
                    )
                    if len(meta_and_ctxs) >= 2:
                        tickers = self._process_hip3_tickers(
                            meta_and_ctxs, dex_name, dex
                        )
                        all_hip3.extend(tickers)
                        logger.info(
                            "Fetched %d tickers from HIP-3 DEX: %s",
                            len(tickers),
                            dex_name,
                        )
                except Exception:
                    logger.exception("Error fetching HIP-3 tickers from %s", dex_name)
        except Exception:
            logger.exception("Error fetching HIP-3 perp DEXs")

        return all_hip3

    def _process_hip3_tickers(
        self,
        meta_and_ctxs: tuple,
        dex_name: str,
        dex_info: dict,
    ) -> list[dict]:
        """Parse HIP-3 DEX tickers."""
        if not meta_and_ctxs or len(meta_and_ctxs) < 2:
            return []

        meta, asset_ctxs = meta_and_ctxs
        universe = meta.get("universe", [])
        if not universe:
            return []

        asset_contexts = asset_ctxs[0] if isinstance(asset_ctxs[0], list) else []

        tickers: list[dict] = []
        for i, item in enumerate(universe):
            symbol = item.get("name", "")
            if not symbol:
                continue
            ctx = asset_contexts[i] if i < len(asset_contexts) else {}

            tickers.append(
                {
                    "symbol": f"{dex_name.lower()}:{symbol}",
                    "name": f"{dex_info.get('fullName', dex_name)}:{symbol}",
                    "is_perpetual": True,
                    "is_hip3": True,
                    "dex_name": dex_name.lower(),
                    "max_leverage": item.get("maxLeverage"),
                    "mark_price": _safe_float(ctx.get("markPx")),
                    "funding_rate": _safe_float(ctx.get("funding")),
                    "open_interest": _safe_float(ctx.get("openInterest")),
                    "day_volume": _safe_float(ctx.get("dayNtlVlm")),
                }
            )

        return tickers


# ── Helpers ───────────────────────────────────────────────────────────────


def _safe_float(value: object) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
