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

    # ── Public API ────────────────────────────────────────────────────

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
        full_symbol = _to_full_symbol(symbol)
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
        full_symbol = _to_full_symbol(symbol)
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
        full_symbol = _to_full_symbol(symbol)
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
