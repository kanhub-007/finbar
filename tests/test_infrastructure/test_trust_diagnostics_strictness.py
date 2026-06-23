"""Spec 2026-06-23 Scenario 10 — strict mode is the default for live-parity.

Trust diagnostics must disclose that ``metric_input_policy`` is ``"strict"``
by default, so callers and Finbot can see that the backtest enforces the
strict input contract (no synthetic dates, no silent defaults, no unknown
annualization).

Classical school, black-box: a real BacktestRunner with deterministic bars.
We assert the trust diagnostics block includes the strictness flag.
"""

from __future__ import annotations

import pandas as pd
from finbar_strategy_runtime.domain.entities.signal_result import SignalResult
from finbar_strategy_runtime.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy

from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _HoldStrategy(TradingStrategy):
    def meta(self) -> StrategyMeta:
        return StrategyMeta(name="hold", variant=DataMode.REAL, description="Hold",
                           required_indicators=[])
    def on_bar(self, b, p) -> SignalResult:
        return SignalResult(action="hold")
    def on_reset(self) -> None:
        pass


def _frame(n=30) -> pd.DataFrame:
    bars = [{"timestamp": f"2026-01-{(i//24)+1:02d}T{i%24:02d}:00:00Z",
             "open": 100+i, "high": 101+i, "low": 99+i, "close": 100.5+i,
             "volume": 1000+i} for i in range(n)]
    return pd.DataFrame(bars).set_index(
        pd.DatetimeIndex(pd.to_datetime([b["timestamp"] for b in bars], utc=True))
    )[["open","high","low","close","volume"]]


class TestStrictModeInTrustDiagnostics:
    def test_trust_diagnostics_include_metric_input_policy_strict(self):
        result = BacktestRunner().run(_frame(), _HoldStrategy(), interval="1d")
        diag = result["trust_diagnostics"]
        assert diag.get("metric_input_policy") == "strict"
