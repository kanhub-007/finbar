"""Unified proxy dispatch tests — spec 2026-06-16_unify-proxy-indicator-dispatch.

Covers Scenarios 1, 2, 3, 5, 6: exact request scope, per-handler dispatch,
ATR-cluster cache sharing, no requires={"atr"}, and short-circuit removal.

Classical school: real ``PandasTaIndicatorCalculator``, real
``UnifiedMetricCatalog``, deterministic fixtures. Assert on OUTCOMES
(which columns appear, non-null tails, value correctness). No mocks.
"""

import inspect
import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog

ALL_PROXIES = [
    "proxy_atr",
    "proxy_vwap",
    "proxy_ibs",
    "proxy_ib_high",
    "proxy_ib_low",
    "proxy_expected_move",
    "proxy_iv",
    "proxy_parkinson",
    "proxy_garman_klass",
    "proxy_rogers_satchell",
    "proxy_typical_price",
    "proxy_ohlc4",
]


@pytest.fixture
def calc() -> PandasTaIndicatorCalculator:
    return PandasTaIndicatorCalculator()


@pytest.fixture
def df_40bar() -> pd.DataFrame:
    """40-bar OHLCV — clears the 14-bar ATR warmup."""
    rng = np.random.default_rng(seed=1)
    n = 40
    close = 100.0 + rng.uniform(-2.0, 2.0, n).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": rng.integers(100, 1000, n).astype(float),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


@pytest.fixture
def df_100bar() -> pd.DataFrame:
    """100-bar OHLCV for parity tests."""
    rng = np.random.default_rng(seed=5)
    n = 100
    close = 100.0 + rng.uniform(-1.5, 1.5, n).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": rng.integers(100, 1000, n).astype(float),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


# =========================================================================
# Scenario 1: Requesting a single proxy returns only that column
# =========================================================================


class TestExactRequestScope:
    """Scenario 1 — request proxy_vwap -> get only proxy_vwap."""

    def test_request_proxy_vwap_does_not_leak_others(self, calc, df_40bar):
        result = calc.calculate(df_40bar, ["proxy_vwap"])
        assert "proxy_vwap" in result.columns

        leaked = [p for p in ALL_PROXIES if p in result.columns and p != "proxy_vwap"]
        assert len(leaked) == 0, f"Leaked columns: {leaked}"

    def test_request_two_proxies_returns_exactly_those(self, calc, df_40bar):
        result = calc.calculate(df_40bar, ["proxy_vwap", "proxy_ibs"])
        assert "proxy_vwap" in result.columns
        assert "proxy_ibs" in result.columns
        assert "proxy_atr" not in result.columns
        assert "proxy_parkinson" not in result.columns

    def test_proxy_alongside_non_proxy(self, calc, df_40bar):
        result = calc.calculate(df_40bar, ["sma_20", "proxy_vwap"])
        assert "sma_20" in result.columns
        assert "proxy_vwap" in result.columns
        assert "proxy_atr" not in result.columns


# =========================================================================
# Scenario 2: Every proxy independently computable (no ordering dependency)
# =========================================================================


class TestEveryProxyIndependentlyComputable:
    """Scenario 2 — each proxy works alone with non-null tail."""

    @pytest.mark.parametrize("name", ALL_PROXIES)
    def test_alone_produces_non_null_tail(self, calc, df_40bar, name):
        result = calc.calculate(df_40bar, [name])
        assert name in result.columns, f"{name} missing from result"

        tail = result[name].tail(5)
        assert tail.notna().any(), f"{name} all-NaN at tail"


# =========================================================================
# Scenario 3: ATR-dependent proxies share computation when co-requested
# =========================================================================


class TestAtrClusterSharesComputation:
    """Scenario 3 — ATR computed once, reused via cache (MACD pattern)."""

    def test_atr_and_ib_high_coexist_and_agree(self, calc, df_40bar):
        result = calc.calculate(df_40bar, ["proxy_atr", "proxy_ib_high"])
        assert "proxy_atr" in result.columns
        assert "proxy_ib_high" in result.columns

        tail = result.tail(10)
        assert tail["proxy_atr"].notna().any()
        assert tail["proxy_ib_high"].notna().any()
        # proxy_ib_high == open + 0.1 * proxy_atr
        np.testing.assert_allclose(
            tail["proxy_ib_high"],
            tail["open"] + 0.1 * tail["proxy_atr"],
            rtol=1e-12,
        )

    def test_all_four_atr_dependents_with_atr(self, calc, df_40bar):
        deps = ["proxy_ib_high", "proxy_ib_low", "proxy_expected_move", "proxy_iv"]
        result = calc.calculate(df_40bar, ["proxy_atr"] + deps)
        for col in deps:
            assert col in result.columns
            assert result[col].tail(5).notna().any()

    def test_ib_high_above_ib_low(self, calc, df_40bar):
        result = calc.calculate(
            df_40bar, ["proxy_ib_high", "proxy_ib_low"]
        )
        tail = result.tail(20)
        assert (tail["proxy_ib_high"] > tail["proxy_ib_low"]).all()


# =========================================================================
# Scenario 5: ATR-dependent handlers do NOT declare requires={"atr"}
# =========================================================================


class TestAtrDependentsNoExternalAtr:
    """Scenario 5 — proxy_ib_high works WITHOUT pandas_ta atr co-requested."""

    def test_proxy_ib_high_without_atr_column(self, calc, df_40bar):
        result = calc.calculate(df_40bar, ["proxy_ib_high"])
        assert "proxy_ib_high" in result.columns
        assert result["proxy_ib_high"].tail(5).notna().any()
        # Must NOT have pulled in a side-effect 'atr' column.
        assert "atr" not in result.columns

    def test_all_atr_deps_work_without_atr(self, calc, df_40bar):
        for name in ("proxy_ib_high", "proxy_ib_low",
                     "proxy_expected_move", "proxy_iv"):
            result = calc.calculate(df_40bar, [name])
            assert name in result.columns
            assert result[name].tail(5).notna().any()
            assert "atr" not in result.columns


# =========================================================================
# Scenario 6: No proxy short-circuit remains in the calculator
# =========================================================================


class TestNoProxyShortCircuit:
    """Scenario 6 — the startswith('proxy_') branch is gone."""

    def test_calculate_source_has_no_proxy_short_circuit(self):
        src = inspect.getsource(PandasTaIndicatorCalculator.calculate)
        assert "proxy_" not in src or "startswith" not in src, (
            "Short-circuit still present in calculate() source"
        )


# =========================================================================
# Scenario 7 (regression): existing proxy behaviour preserved
# =========================================================================


class TestLegitimateMultiProxyRegression:
    """Scenario 7 — requesting all four ATR-cluster proxies together works."""

    def test_four_atr_cluster_together(self, calc, df_40bar):
        result = calc.calculate(df_40bar, [
            "proxy_atr", "proxy_ib_high", "proxy_ib_low", "proxy_expected_move",
        ])
        for name in ("proxy_atr", "proxy_ib_high",
                     "proxy_ib_low", "proxy_expected_move"):
            assert name in result.columns
            assert result[name].tail(5).notna().any()
        assert (result["proxy_ib_high"].tail(20) > result["proxy_ib_low"].tail(20)).all()

    def test_order_independence_still_holds(self, calc, df_100bar):
        """proxy_ib_high before vs after pandas_ta 'atr' -> same value."""
        proxy_first = calc.calculate(
            df_100bar.copy(), ["proxy_ib_high", "atr"]
        )["proxy_ib_high"]
        atr_first = calc.calculate(
            df_100bar.copy(), ["atr", "proxy_ib_high"]
        )["proxy_ib_high"]
        pd.testing.assert_series_equal(proxy_first, atr_first)


# =========================================================================
# Scenario 4: check_metric honest for all 12 proxies by construction
# =========================================================================


class TestCheckMetricHonesty:
    """Scenario 4 — each proxy reports computable=True; all share PROXY family."""

    def test_catalog_constructs_without_raising(self):
        """The construction-time consistency check passes (handler == registry)."""
        # If any registry entry lacks a handler (or vice versa), __init__ raises.
        UnifiedMetricCatalog()  # raises RuntimeError on inconsistency

    @pytest.mark.parametrize("name", ALL_PROXIES)
    def test_each_proxy_computable_on_daily(self, name):
        catalog = UnifiedMetricCatalog()
        result = catalog.check(name, "daily_ohlcv")
        assert result.computable is True, f"{name}: {result.warnings}"

    def test_all_twelve_share_proxy_family(self):
        from finbar_strategy_runtime.domain.entities.metric_family import (
            MetricFamily,
        )

        catalog = UnifiedMetricCatalog()
        proxy_metrics = catalog.list(MetricFamily.PROXY)
        names = {m.name for m in proxy_metrics}
        assert names == set(ALL_PROXIES), (
            f"Missing: {set(ALL_PROXIES) - names}, "
            f"Extra: {names - set(ALL_PROXIES)}"
        )
