"""Tests for metric catalog API routes — Slice 4."""

import pytest
from fastapi.testclient import TestClient

from finbar.startup.api import create_app


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestListMarketMetricsRoute:
    def test_list_returns_metrics(self, client):
        """GET /api/metrics returns a list of metrics."""
        response = client.get("/api/metrics", params={"interval": "1d"})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 50

    def test_list_includes_corwin_schultz(self, client):
        """The list includes corwin_schultz_spread."""
        response = client.get("/api/metrics", params={"interval": "1d"})
        data = response.json()
        names = {m["name"] for m in data}
        assert "corwin_schultz_spread" in names

    def test_list_filter_by_family(self, client):
        """Family filter narrows results."""
        response = client.get("/api/metrics", params={"family": "spread"})
        data = response.json()
        assert len(data) > 0
        assert all(m["family"] == "spread" for m in data)


class TestCheckMetricRoute:
    def test_check_amihud_computable(self, client):
        """GET /api/metrics/check/amihud_illiq → computable."""
        response = client.get(
            "/api/metrics/check/amihud_illiq", params={"data_class": "daily_ohlcv"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["supported"] is True
        assert data["computable"] is True

    def test_check_unknown_not_supported(self, client):
        """GET /api/metrics/check/nonexistent → supported=False."""
        response = client.get(
            "/api/metrics/check/nonexistent", params={"data_class": "daily_ohlcv"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["supported"] is False


class TestResolveMetricRoute:
    def test_resolve_volatility_daily(self, client):
        """GET /api/metrics/resolve/volatility → yang_zhang_vol."""
        response = client.get(
            "/api/metrics/resolve/volatility",
            params={"data_class": "daily_ohlcv", "interval": "1d"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["selected_metric"] == "yang_zhang_vol"
        assert data["confidence"] == "proxy"

    def test_resolve_volatility_intraday(self, client):
        """GET /api/metrics/resolve/volatility → realized_vol_5m."""
        response = client.get(
            "/api/metrics/resolve/volatility",
            params={"data_class": "intraday_ohlcv", "interval": "5min"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["selected_metric"] == "realized_vol_5m"
        assert data["confidence"] == "actual"
