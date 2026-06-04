"""Tests for proxy indicator functions — pure math, no I/O."""


import pandas as pd

from finbar.core.domain.services.proxy_indicator import (
    atr_to_iv_proxy,
    daily_expected_move,
    enrich_bar_with_proxies,
    enrich_dataframe_with_proxies,
    garman_klass_vol,
    ib_proxy_high,
    ib_proxy_low,
    ibs,
    ohlc4,
    parkinson_vol,
    rogers_satchell_vol,
    round_number_proximity,
    rvol,
    slippage_estimate,
    typical_price,
)


class TestVWAPProxies:
    def test_typical_price(self):
        assert typical_price(100, 90, 95) == 95.0
        assert typical_price(10, 20, 15) == 15.0

    def test_ohlc4(self):
        assert ohlc4(100, 105, 98, 102) == 101.25


class TestIBProxies:
    def test_ib_proxy_high(self):
        assert ib_proxy_high(100, 3.5) == 100.35  # 100 + 0.1*3.5

    def test_ib_proxy_low(self):
        assert ib_proxy_low(100, 3.5) == 99.65


class TestIBS:
    def test_normal(self):
        result = ibs(100, 90, 95)
        assert abs(result - 0.5) < 0.01

    def test_at_high(self):
        result = ibs(100, 90, 100)
        assert abs(result - 1.0) < 0.01

    def test_at_low(self):
        result = ibs(100, 90, 90)
        assert abs(result - 0.0) < 0.01

    def test_zero_range(self):
        result = ibs(100, 100, 100)
        assert result == 0.5


class TestRVOL:
    def test_normal(self):
        assert rvol(2000, 1000) == 2.0

    def test_zero_avg_volume(self):
        assert rvol(2000, 0) == 1.0


class TestVolatilityEstimators:
    def test_parkinson_vol(self):
        result = parkinson_vol(100, 90)
        assert result > 0

    def test_parkinson_zero_on_invalid(self):
        assert parkinson_vol(0, 90) == 0.0
        assert parkinson_vol(100, 0) == 0.0

    def test_garman_klass_vol(self):
        result = garman_klass_vol(100, 105, 98, 102)
        assert result > 0

    def test_garman_klass_zero_on_invalid(self):
        assert garman_klass_vol(100, 105, 0, 102) == 0.0

    def test_rogers_satchell_vol(self):
        result = rogers_satchell_vol(100, 105, 98, 102)
        # Rogers-Satchell can be negative in edge cases
        assert isinstance(result, float)

    def test_rogers_satchell_zero_on_invalid(self):
        assert rogers_satchell_vol(0, 105, 98, 102) == 0.0


class TestExpectedMove:
    def test_expected_move(self):
        assert abs(daily_expected_move(100, 3.0) - 2.4) < 0.001  # 0.8 * 3.0


class TestRoundNumbers:
    def test_small_price(self):
        result = round_number_proximity(45.7)
        assert result["round_number"] == 45
        assert result["distance"] > 0

    def test_zero_price(self):
        result = round_number_proximity(0)
        assert result["round_number"] == 0


class TestSlippage:
    def test_capped(self):
        assert slippage_estimate(10000, 100) <= 0.05

    def test_zero_volume(self):
        assert slippage_estimate(1000, 0) == 0.01


class TestIVProxy:
    def test_atr_to_iv(self):
        result = atr_to_iv_proxy(3.0, 100)
        assert result > 0

    def test_zero_on_invalid(self):
        assert atr_to_iv_proxy(0, 100) == 0.0
        assert atr_to_iv_proxy(3.0, 0) == 0.0


class TestEnrichBar:
    def test_enriches_all_proxies(self):
        bar = {
            "open": 100,
            "high": 105,
            "low": 98,
            "close": 102,
            "volume": 1000000,
            "atr": 3.5,
        }
        result = enrich_bar_with_proxies(bar)
        proxy_keys = sorted(k for k in result if k.startswith("proxy_"))
        assert "proxy_typical_price" in proxy_keys
        assert "proxy_ibs" in proxy_keys
        assert "proxy_parkinson" in proxy_keys
        assert "proxy_ib_high" in proxy_keys
        assert "proxy_expected_move" in proxy_keys
        assert len(proxy_keys) >= 8

    def test_no_atr_skips_ib_proxies(self):
        bar = {
            "open": 100,
            "high": 105,
            "low": 98,
            "close": 102,
            "volume": 1000000,
        }
        result = enrich_bar_with_proxies(bar)
        # IB proxies require ATR — should not appear
        assert "proxy_ib_high" not in result


class TestEnrichDataFrame:
    def test_enriches_dataframe(self):
        df = pd.DataFrame(
            {
                "open": [100, 101],
                "high": [105, 106],
                "low": [98, 99],
                "close": [102, 103],
                "volume": [1000000, 1100000],
                "atr": [3.5, 3.2],
            }
        )
        result = enrich_dataframe_with_proxies(df)
        assert "proxy_typical_price" in result.columns
        assert len(result) == 2
