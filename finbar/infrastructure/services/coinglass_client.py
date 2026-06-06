"""CoinGlassClient — CoinGlass API v4 implementation of DerivativesDataProvider.

Uses CoinGlassRateLimiter (sliding‑window, same pattern as YF/HL).
Supports funding rate, aggregated CVD, and open interest history.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from finbar.core.domain.interfaces.derivatives_data_provider import (
    DerivativesDataProvider,
)
from finbar.infrastructure.services.coinglass_rate_limiter import (
    CoinGlassRateLimiter,
)

logger = logging.getLogger(__name__)

_COINGLASS_BASE = "https://open-api-v4.coinglass.com"
_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0


class CoinGlassClient(DerivativesDataProvider):
    """CoinGlass Open API v4 client for derivatives market data.

    Requires ``COINGLASS_API_KEY`` environment variable.
    Rate limiting matches the existing YahooFinanceRateLimiter pattern
    (sliding window, thread‑safe), with dynamic limit updates from
    CoinGlass response headers.
    """

    EXCHANGES = ["Binance", "OKX", "coinbase", "Kraken", "Bybit"]

    _FALLBACK_FORMATS: dict[str, str] = {
        "Binance": "{base}USDT",
        "Bybit": "{base}USDT",
        "OKX": "{base}-USDT-SWAP",
        "coinbase": "{base}-USD",
        "Kraken": "PF_{base}USD",
    }

    def __init__(
        self,
        api_key: str | None = None,
        rate_limiter: CoinGlassRateLimiter | None = None,
    ):
        self._api_key = api_key or os.getenv("COINGLASS_API_KEY", "")
        if not self._api_key:
            logger.warning("COINGLASS_API_KEY not set — CoinGlassClient will fail")
        self._session = requests.Session()
        self._session.headers.update(
            {"accept": "application/json", "CG-API-KEY": self._api_key}
        )
        self._rate_limiter = rate_limiter or CoinGlassRateLimiter()
        self._supported_pairs: dict[str, list[dict]] = {}
        self._symbol_exchange_map: dict[str, list[str]] = {}
        self._pairs_loaded = False

    # ── Public API ────────────────────────────────────────────────────

    def load_supported_pairs(self) -> None:
        """Fetch and cache supported exchange pairs from CoinGlass."""
        if self._pairs_loaded:
            return
        raw = self._get("/api/futures/supported-exchange-pairs", {})
        pairs_data = raw[0] if isinstance(raw, list) and raw and isinstance(raw[0], dict) else {}
        if not pairs_data and isinstance(raw, list):
            # Response might be nested differently
            pairs_data = {}

        # Re-fetch with correct parsing — the endpoint returns {code, data: {exchange: [pairs]}}
        self._supported_pairs.clear()
        self._symbol_exchange_map.clear()
        # We already called _get which returns data.data — let's do a raw call
        self._require_key()
        self._rate_limiter.wait()
        url = f"{_COINGLASS_BASE}/api/futures/supported-exchange-pairs"
        resp = self._session.get(url, timeout=30)
        self._rate_limiter.update_from_headers(dict(resp.headers))
        resp.raise_for_status()
        body = resp.json()
        pairs_data = body.get("data", {})

        for exchange, pairs in pairs_data.items():
            if exchange in self.EXCHANGES:
                self._supported_pairs[exchange] = pairs
                for p in pairs:
                    base = str(p.get("base_asset", "")).upper()
                    if base:
                        self._symbol_exchange_map.setdefault(base, [])
                        if exchange not in self._symbol_exchange_map[base]:
                            self._symbol_exchange_map[base].append(exchange)
        self._pairs_loaded = True
        total = sum(len(v) for v in self._supported_pairs.values())
        logger.info(
            "CoinGlass: loaded %d pairs from %d exchanges",
            total, len(self._supported_pairs),
        )

    def get_supported_exchanges(self, symbol: str) -> list[str]:
        """Return exchanges that support the given base symbol."""
        if not self._pairs_loaded:
            self.load_supported_pairs()
        return self._symbol_exchange_map.get(symbol.upper(), [])

    def _get_full_symbol(self, base_symbol: str, exchange: str) -> str | None:
        """Get the full instrument ID for a base symbol on an exchange."""
        if not self._pairs_loaded:
            self.load_supported_pairs()
        pairs = self._supported_pairs.get(exchange, [])
        for p in pairs:
            if str(p.get("base_asset", "")).upper() == base_symbol.upper():
                return p.get("instrument_id")
        # Fallback to known formats
        fmt = self._FALLBACK_FORMATS.get(exchange)
        if fmt:
            base = base_symbol.upper()
            if exchange == "Kraken" and base == "BTC":
                return "PF_XBTUSD"
            return fmt.format(base=base)
        return f"{base_symbol}USDT"

    def fetch(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: str | None = None,
        end_time: str | None = None,
        exchange: str = "Binance",
        limit: int = 500,
    ) -> list[DerivativesMetrics]:
        """Fetch funding rate history for a symbol."""
        self._require_key()
        full_symbol = self._get_full_symbol(symbol, exchange) or _to_full_symbol(symbol)
        params = _params(full_symbol, interval, exchange, limit, start_time, end_time)
        raw = self._get("/api/futures/funding-rate/history", params)
        return _parse_funding(raw, symbol, interval)

    def fetch_cvd(
        self,
        symbol: str,
        interval: str = "1h",
        exchange: str = "Binance",
        limit: int = 500,
    ) -> list[DerivativesMetrics]:
        """Fetch aggregated CVD history."""
        self._require_key()
        full_symbol = self._get_full_symbol(symbol, exchange) or _to_full_symbol(symbol)
        params = {
            "exchange_list": exchange,
            "symbol": full_symbol,
            "interval": interval,
            "limit": limit,
        }
        raw = self._get("/api/futures/aggregated-cvd/history", params)
        return _parse_cvd(raw, symbol, interval)

    def fetch_open_interest(
        self,
        symbol: str,
        interval: str = "1h",
        exchange: str = "Binance",
        limit: int = 500,
    ) -> list[DerivativesMetrics]:
        """Fetch aggregated open interest history."""
        self._require_key()
        full_symbol = self._get_full_symbol(symbol, exchange) or _to_full_symbol(symbol)
        params = {
            "exchange_list": exchange,
            "symbol": full_symbol,
            "interval": interval,
            "limit": limit,
        }
        raw = self._get("/api/futures/open-interest/aggregated-history", params)
        return _parse_oi(raw, symbol, interval)

    # ── HTTP helpers ──────────────────────────────────────────────────

    def _require_key(self) -> None:
        if not self._api_key:
            raise RuntimeError("COINGLASS_API_KEY not configured")

    def _get(self, endpoint: str, params: dict[str, Any]) -> list[dict]:
        self._rate_limiter.wait()
        url = f"{_COINGLASS_BASE}{endpoint}"
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=30)
                self._rate_limiter.update_from_headers(dict(resp.headers))
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "0":
                    raise RuntimeError(f"CoinGlass API error: {data.get('msg', 'unknown')}")
                return data.get("data", [])
            except requests.RequestException as exc:
                last_error = exc
                if resp is not None and resp.status_code == 429:
                    self._rate_limiter.on_rate_limit_error(attempt)
                backoff = _BASE_BACKOFF ** (attempt + 1)
                logger.warning(
                    "CoinGlass request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, exc, backoff,
                )
                time.sleep(backoff)
        raise RuntimeError(
            f"CoinGlass request failed after {_MAX_RETRIES} attempts: {last_error}"
        )


# ── module helpers ──────────────────────────────────────────────────────


def _to_full_symbol(symbol: str) -> str:
    return f"{symbol}USDT" if "USDT" not in symbol else symbol


def _params(
    symbol: str,
    interval: str,
    exchange: str,
    limit: int,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    p: dict[str, Any] = {
        "exchange": exchange,
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if start_time:
        p["startTime"] = start_time
    if end_time:
        p["endTime"] = end_time
    return p


def _parse_funding(raw: list[dict], symbol: str, interval: str) -> list[DerivativesMetrics]:
    of = _opt_float
    return [
        DerivativesMetrics(
            symbol=symbol,
            timestamp=_parse_ts(item),
            interval=interval,
            funding_rate=of(item.get("close") or item.get("fundingRate")),
        )
        for item in raw
    ]


def _parse_cvd(raw: list[dict], symbol: str, interval: str) -> list[DerivativesMetrics]:
    of = _opt_float
    return [
        DerivativesMetrics(
            symbol=symbol,
            timestamp=_parse_ts(item),
            interval=interval,
            cumulative_volume_delta=of(item.get("close") or item.get("cvd")),
        )
        for item in raw
    ]


def _parse_oi(raw: list[dict], symbol: str, interval: str) -> list[DerivativesMetrics]:
    of = _opt_float
    return [
        DerivativesMetrics(
            symbol=symbol,
            timestamp=_parse_ts(item),
            interval=interval,
            open_interest=of(item.get("close") or item.get("openInterest")),
        )
        for item in raw
    ]


def _parse_ts(item: dict) -> str:
    ts = item.get("createTime") or item.get("time") or 0
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return str(ts)


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
