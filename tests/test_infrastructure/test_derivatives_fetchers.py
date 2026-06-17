"""Tests for new derivatives fetchers — Slice 6 Scenarios 6.1–6.3.

These are integration tests that skip when no API key is available.
The parser functions are unit-tested separately.
"""

import os

import pytest

from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from finbar.infrastructure.services.coinglass_client import (
    _parse_liquidations,
    _parse_long_short,
)
from finbar.infrastructure.services.hyperliquid_fetcher import _parse_hl_funding

# ---------------------------------------------------------------------------
# Unit tests for parsers (no network)
# ---------------------------------------------------------------------------


class TestLiquidationParser:
    """_parse_liquidations handles various field name conventions."""

    def test_parses_long_short_usd(self):
        """Standard field names long_usd / short_usd."""
        raw = [
            {
                "time": 1704067200000,
                "long_usd": 1_500_000,
                "short_usd": 800_000,
            }
        ]
        result = _parse_liquidations(raw, "BTC", "1h")
        assert len(result) == 1
        assert result[0].liquidations_long_1h == 1_500_000
        assert result[0].liquidations_short_1h == 800_000

    def test_parses_camel_case_fields(self):
        """Camel-case field names longUsd / shortUsd."""
        raw = [{"time": 1704067200000, "longUsd": 100, "shortUsd": 200}]
        result = _parse_liquidations(raw, "BTC", "1h")
        assert result[0].liquidations_long_1h == 100
        assert result[0].liquidations_short_1h == 200

    def test_missing_fields_produce_none(self):
        """Missing fields → None."""
        raw = [{"time": 1704067200000}]
        result = _parse_liquidations(raw, "BTC", "1h")
        assert result[0].liquidations_long_1h is None
        assert result[0].liquidations_short_1h is None

    def test_empty_raw(self):
        """Empty list → empty result."""
        assert _parse_liquidations([], "BTC", "1h") == []


class TestLongShortParser:
    """_parse_long_short handles various field name conventions."""

    def test_parses_ratio(self):
        """Standard field name ratio."""
        raw = [{"time": 1704067200000, "ratio": 1.5}]
        result = _parse_long_short(raw, "BTC", "1h")
        assert result[0].long_short_ratio == 1.5

    def test_parses_long_short_ratio(self):
        """Full field name long_short_ratio."""
        raw = [{"time": 1704067200000, "long_short_ratio": 2.0}]
        result = _parse_long_short(raw, "BTC", "1h")
        assert result[0].long_short_ratio == 2.0

    def test_empty_raw(self):
        """Empty list → empty result."""
        assert _parse_long_short([], "BTC", "1h") == []


class TestHLFundingParser:
    """_parse_hl_funding parses Hyperliquid funding_history output."""

    def test_parses_funding_rate(self):
        """Standard item with time + fundingRate."""
        raw = [{"time": 1704067200000, "fundingRate": "0.00012500"}]
        result = _parse_hl_funding(raw, "BTC", "1h")
        assert len(result) == 1
        assert abs(result[0].funding_rate - 0.000125) < 1e-9

    def test_skips_missing_fields(self):
        """Items missing time or fundingRate are skipped."""
        raw = [
            {"time": 1704067200000, "fundingRate": "0.001"},
            {"time": 1704067300000},  # missing fundingRate
            {"fundingRate": "0.002"},  # missing time
        ]
        result = _parse_hl_funding(raw, "BTC", "1h")
        assert len(result) == 1

    def test_empty_raw(self):
        """Empty list → empty result."""
        assert _parse_hl_funding([], "BTC", "1h") == []


# ---------------------------------------------------------------------------
# Integration tests (skip without API key / network)
# ---------------------------------------------------------------------------

_coinglass_key = pytest.mark.skipif(
    not os.getenv("COINGLASS_API_KEY"), reason="COINGLASS_API_KEY not set"
)


@_coinglass_key
class TestCoinGlassLiquidationsIntegration:
    def test_fetch_liquidations_returns_data(self):
        from finbar.infrastructure.services.coinglass_client import CoinGlassClient

        client = CoinGlassClient()
        metrics = client.fetch_liquidations("BTC", interval="1h", limit=10)
        assert len(metrics) > 0
        assert isinstance(metrics[0], DerivativesMetrics)


@_coinglass_key
class TestCoinGlassLongShortIntegration:
    def test_fetch_long_short_ratio_returns_data(self):
        from finbar.infrastructure.services.coinglass_client import CoinGlassClient

        client = CoinGlassClient()
        metrics = client.fetch_long_short_ratio("BTC", interval="1h", limit=10)
        assert len(metrics) > 0
        assert metrics[0].long_short_ratio is not None


class TestHyperliquidFundingIntegration:
    """Hyperliquid funding_history is free (no API key needed)."""

    def test_fetch_funding_history_returns_data(self):
        from finbar.infrastructure.services.hyperliquid_fetcher import (
            HyperliquidFetcher,
        )

        fetcher = HyperliquidFetcher()
        bars = fetcher.fetch_funding_history("BTC", interval="1h")
        assert len(bars) > 0
        assert bars[0].funding_rate is not None
