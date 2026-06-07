"""Tests for compact server-side backtest result access."""

from finbar.core.application.use_cases.get_backtest_equity import (
    GetBacktestEquityUseCase,
)
from finbar.core.application.use_cases.get_backtest_summary import (
    GetBacktestSummaryUseCase,
)
from finbar.core.application.use_cases.get_backtest_trades import (
    GetBacktestTradesUseCase,
)
from finbar.core.application.use_cases.list_backtest_results import (
    ListBacktestResultsUseCase,
)
from finbar.core.application.use_cases.store_backtest_result import (
    StoreBacktestResultUseCase,
)
from finbar.infrastructure.services.in_memory_backtest_result_store import (
    InMemoryBacktestResultStore,
)


def _result() -> dict:
    return {
        "strategy_name": "demo_strategy",
        "symbol": "BTC-USD",
        "interval": "5min",
        "start_date": "2024-01-01",
        "end_date": "2024-01-03",
        "bar_count": 3,
        "initial_cash": 10000,
        "final_value": 10100,
        "total_return": 0.01,
        "total_trades": 2,
        "winning_trades": 1,
        "losing_trades": 1,
        "win_rate": 0.5,
        "max_drawdown": -0.02,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.4,
        "profit_factor": 1.5,
        "calmar_ratio": 0.5,
        "trades": [
            {"entry_date": "2024-01-01", "net_pnl": -20, "duration_bars": 3},
            {"entry_date": "2024-01-02", "net_pnl": 120, "duration_bars": 5},
        ],
        "equity_curve": [
            {"date": "2024-01-01 00:00:00", "value": 10000, "drawdown": 0},
            {"date": "2024-01-01 00:05:00", "value": 9900, "drawdown": -0.01},
            {"date": "2024-01-02 00:00:00", "value": 10100, "drawdown": 0},
        ],
        "analytics": {"monthly_returns": {}},
        "trust_diagnostics": {"lookahead_safe_mtf": True},
        "diagnostics": [],
        "error": None,
    }


class TestBacktestResultAccess:
    def test_store_returns_summary_without_large_arrays(self):
        """Storing a result returns a compact response with access pointers."""
        store = InMemoryBacktestResultStore()
        result = StoreBacktestResultUseCase(store).execute(_result())

        response = result.response

        assert result.result_id.startswith("bt_")
        assert response["ids"]["result_id"] == result.result_id
        assert response["counts"]["trades"] == 2
        assert response["returned"]["trades"] == 0
        assert "result" not in response
        assert "get_backtest_trades" in response["access"]["trades"]

    def test_summary_can_return_full_detail_when_explicit(self):
        """Full detail remains available when explicitly requested."""
        store = InMemoryBacktestResultStore()
        result_id = StoreBacktestResultUseCase(store).execute(_result()).result_id

        summary = GetBacktestSummaryUseCase(store).execute(result_id, "full")

        assert summary.found is True
        assert summary.response["returned"]["trades"] == 2
        assert len(summary.response["result"]["equity_curve"]) == 3

    def test_trade_access_is_paginated_and_sortable(self):
        """Stored trades can be fetched one page at a time."""
        store = InMemoryBacktestResultStore()
        result_id = StoreBacktestResultUseCase(store).execute(_result()).result_id

        trades = GetBacktestTradesUseCase(store).execute(
            result_id,
            page=0,
            page_size=1,
            sort_by="net_pnl",
            sort_dir="desc",
        )

        assert trades.found is True
        assert trades.trade_count == 1
        assert trades.total_trades == 2
        assert trades.total_pages == 2
        assert trades.trades[0]["net_pnl"] == 120

    def test_equity_access_downsamples_daily(self):
        """Daily equity mode returns one point per day."""
        store = InMemoryBacktestResultStore()
        result_id = StoreBacktestResultUseCase(store).execute(_result()).result_id

        equity = GetBacktestEquityUseCase(store).execute(result_id, mode="daily")

        assert equity.found is True
        assert equity.equity_count == 2
        assert equity.equity_curve[0]["date"] == "2024-01-01 00:05:00"
        assert equity.equity_curve[1]["date"] == "2024-01-02 00:00:00"

    def test_result_listing_filters_by_symbol(self):
        """Stored result metadata is discoverable without large arrays."""
        store = InMemoryBacktestResultStore()
        StoreBacktestResultUseCase(store).execute(_result())

        listing = ListBacktestResultsUseCase(store).execute(symbol="BTC-USD")

        assert len(listing.results) == 1
        assert listing.results[0]["symbol"] == "BTC-USD"
        assert listing.results[0]["total_trades"] == 2
