"""API route tests using FastAPI TestClient.

Smoke tests for all endpoint groups — health, symbols, prices, jobs, analysis.
"""

import pytest
from fastapi.testclient import TestClient

from finbar.startup.api import create_app


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestHealth:
    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_sources(self, client):
        response = client.get("/api/sources")
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        sources = data["sources"]
        assert "yfinance" in sources
        assert "hyperliquid" in sources


class TestSymbols:
    def test_cached_symbols_empty(self, client):
        response = client.get("/api/symbols/cached")
        assert response.status_code == 200
        data = response.json()
        if isinstance(data, dict):
            assert "symbols" in data
            assert isinstance(data["symbols"], list)
        else:
            assert isinstance(data, list)

    def test_symbol_info_not_found(self, client):
        response = client.get("/api/symbols/info/ZZZZNONEXISTENT")
        assert response.status_code in (200, 404)


class TestPrices:
    def test_cached_prices_empty(self, client):
        response = client.get(
            "/api/prices/cached",
            params={
                "symbol": "NONEXISTENT123",
                "source": "yfinance",
                "interval": "1d",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["bar_count"] == 0

    def test_delete_cached_requires_symbol(self, client):
        response = client.delete(
            "/api/prices/cached", params={"symbol": "NONEXISTENT123"}
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 0


class TestAnalysis:
    def test_list_strategies(self, client):
        response = client.get("/api/analysis/strategies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = [s["name"] for s in data]
        assert "sma_crossover" in names
        assert "rsi_mean_reversion" in names
        assert "auction_drive" in names

    def test_apply_indicators_empty(self, client):
        response = client.post(
            "/api/analysis/indicators",
            json={"bars": [], "indicators": ["rsi_14"]},
        )
        assert response.status_code == 400

    def test_apply_indicators_missing_columns(self, client):
        bars = [{"timestamp": "2024-01-01", "close": 100}]
        response = client.post(
            "/api/analysis/indicators",
            json={"bars": bars, "indicators": ["rsi_14"]},
        )
        assert response.status_code == 400

    def test_apply_indicators_success(self, client):
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000000,
            },
            {
                "timestamp": "2024-01-02",
                "open": 102,
                "high": 107,
                "low": 100,
                "close": 104,
                "volume": 1100000,
            },
        ]
        response = client.post(
            "/api/analysis/indicators",
            json={"bars": bars, "indicators": ["sma_3"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["bar_count"] == 2
        assert "sma_3" in data["indicators_applied"]

    def test_run_backtest_empty_bars(self, client):
        response = client.post(
            "/api/analysis/backtest",
            json={
                "bars": [],
                "strategy_name": "sma_crossover",
            },
        )
        assert response.status_code == 400

    def test_run_backtest_unknown_strategy(self, client):
        bars = [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 102,
                "volume": 1000000,
            }
        ]
        response = client.post(
            "/api/analysis/backtest",
            json={
                "bars": bars,
                "strategy_name": "nonexistent",
            },
        )
        assert response.status_code == 400

    def test_run_backtest_success(self, client):

        bars = [
            {
                "timestamp": f"2024-01-{day:02d}",
                "open": 100 + i * 0.5,
                "high": 102 + i * 0.5,
                "low": 99 + i * 0.5,
                "close": 101 + i * 0.5,
                "volume": 1000000,
                # Pre-compute indicators so backtest works
                "sma_20": 100 + i * 0.5,
                "sma_50": 99 + i * 0.5,
            }
            for i, day in enumerate(range(1, 21), start=0)
        ]
        response = client.post(
            "/api/analysis/backtest",
            json={
                "bars": bars,
                "strategy_name": "sma_crossover",
                "symbol": "TEST",
                "interval": "1d",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_return" in data
        assert "sharpe_ratio" in data
        assert "trades" in data


class TestJobs:
    def test_job_status_not_found(self, client):
        response = client.get("/api/jobs/nonexistent-job-id")
        assert response.status_code in (200, 404)
