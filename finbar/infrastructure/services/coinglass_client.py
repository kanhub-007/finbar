"""CoinGlassClient — CoinGlass API implementation of DerivativesDataProvider.

Handles HTTP authentication, rate limiting, and response parsing.
Implements the domain‑layer DerivativesDataProvider interface.
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

logger = logging.getLogger(__name__)

_COINGLASS_BASE = "https://open-api-v3.coinglass.com/api"
_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0


class CoinGlassClient(DerivativesDataProvider):
    """CoinGlass Open API v3 client for derivatives market data.

    Requires ``COINGLASS_API_KEY`` environment variable.
    Supports perpetual futures data: OI, CVD, funding rate,
    long/short ratio, and liquidations.
    """

    def __init__(self, api_key: str | None = None):
        """Create the client.

        Args:
            api_key: CoinGlass API key. Falls back to
                ``COINGLASS_API_KEY`` environment variable.
        """
        self._api_key = api_key or os.getenv("COINGLASS_API_KEY", "")
        if not self._api_key:
            logger.warning("COINGLASS_API_KEY not set — CoinGlassClient will fail")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "accept": "application/json",
                "coinglassSecret": self._api_key,
            }
        )

    def fetch(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[DerivativesMetrics]:
        """Fetch funding rate history for a symbol.

        CoinGlass open API provides funding rate, OI, and liquidations
        through separate endpoints. This implementation fetches funding
        rate history as the primary time series; other metrics can be
        added via additional endpoints in future iterations.

        Args:
            symbol: Ticker (e.g. "BTC").
            interval: Bar interval ("1h", "4h", "1d").
            start_time: Unix milliseconds start.
            end_time: Unix milliseconds end.

        Returns:
            List of DerivativesMetrics with funding rate, OI, and CVD.
        """
        if not self._api_key:
            raise RuntimeError("COINGLASS_API_KEY not configured")

        params = self._build_params(symbol, interval, start_time, end_time)
        raw = self._get_with_retry(
            f"{_COINGLASS_BASE}/futures/fundingRateHistory",
            params,
        )
        return self._parse_response(raw, symbol, interval)

    # ── request helpers ───────────────────────────────────────────────

    def _build_params(
        self,
        symbol: str,
        interval: str,
        start_time: str | None,
        end_time: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return params

    def _get_with_retry(
        self,
        url: str,
        params: dict,
    ) -> list[dict]:
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "0":
                    raise RuntimeError(
                        f"CoinGlass API error: {data.get('msg', 'unknown')}"
                    )
                return data.get("data", [])
            except requests.RequestException as exc:
                last_error = exc
                backoff = _BASE_BACKOFF ** (attempt + 1)
                logger.warning(
                    "CoinGlass request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
        raise RuntimeError(
            f"CoinGlass request failed after {_MAX_RETRIES} attempts: {last_error}"
        )

    # ── response parsing ──────────────────────────────────────────────

    @staticmethod
    def _parse_response(
        raw: list[dict],
        symbol: str,
        interval: str,
    ) -> list[DerivativesMetrics]:
        return [
            CoinGlassClient._item_to_metrics(item, symbol, interval)
            for item in raw
        ]

    @staticmethod
    def _item_to_metrics(
        item: dict,
        symbol: str,
        interval: str,
    ) -> DerivativesMetrics:
        of = CoinGlassClient._opt_float
        return DerivativesMetrics(
            symbol=symbol,
            timestamp=CoinGlassClient._parse_timestamp(item),
            interval=interval,
            open_interest=of(item.get("openInterest")),
            open_interest_delta_1h=of(item.get("h1OIChangePercent")),
            open_interest_delta_24h=of(item.get("h24OIChangePercent")),
            funding_rate=of(item.get("fundingRate")),
            cumulative_volume_delta=of(item.get("cvd")),
            long_short_ratio=of(item.get("longShortRatio")),
            liquidations_long_1h=of(item.get("longLiquidationUsd")),
            liquidations_short_1h=of(item.get("shortLiquidationUsd")),
        )

    @staticmethod
    def _parse_timestamp(item: dict) -> str:
        ts = item.get("createTime") or item.get("time") or 0
        try:
            return datetime.fromtimestamp(
                int(ts) / 1000, tz=timezone.utc
            ).isoformat()
        except (ValueError, OSError):
            return str(ts)

    @staticmethod
    def _opt_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
