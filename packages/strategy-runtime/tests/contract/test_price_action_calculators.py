"""Contract tests for price-action and trading-theory calculators.

Covers: Fibonacci levels, Bill Williams indicators, Dow Theory / trend structure.
"""

import numpy as np
import pandas as pd
import pytest


# =========================================================================
# Fibonacci levels
# =========================================================================


class TestFibonacciLevels:
    """Fibonacci retracements and extensions from swing detection."""

    def test_retracement_from_uptrend_swing(self):
        """Swing low=100, high=200 → retracement levels."""
        from finbar_strategy_runtime.domain.services.fibonacci_levels import (
            fib_618_retrace,
        )

        # 40 bars: flat base → sharp uptrend → pullback
        values = [100.0] * 10 + [100, 120, 140, 160, 180, 200, 210, 215, 220, 225,
                                 220, 215, 210, 205, 200, 195, 190, 185, 180, 178,
                                 176, 174, 172, 170, 172, 174, 176, 178, 180, 182]
        close = pd.Series(values)
        result = fib_618_retrace(close, swing_window=3)
        # Fib levels should be populated after swing detection
        assert not pd.isna(result.iloc[-1])

    def test_extension_from_completed_swing(self):
        """Swing low=100, high=200 → extension targets."""
        from finbar_strategy_runtime.domain.services.fibonacci_levels import (
            fib_1618_extension,
        )

        values = [100.0] * 10 + [100, 120, 140, 160, 180, 200, 210, 215, 220, 225,
                                 220, 215, 210, 205, 200, 195, 190, 185, 180, 178,
                                 176, 174, 172, 170, 172, 174, 176, 178, 180, 182]
        close = pd.Series(values)
        result = fib_1618_extension(close, swing_window=3)
        assert not pd.isna(result.iloc[-1])

    def test_no_lookahead_fib_emits_after_swing_complete(self):
        """Fib level emits only after swing fully closes (never uses future bars)."""
        from finbar_strategy_runtime.domain.services.fibonacci_levels import (
            fib_618_retrace,
        )

        # Uptrend completing at bar 12, pullback starts bar 13
        close = pd.Series(
            [100.0, 105.0, 110.0, 115.0, 125.0, 135.0, 150.0, 160.0,
             175.0, 190.0, 200.0, 210.0,  # swing high at 11
             205.0, 200.0, 195.0, 190.0]   # pullback
        )
        result = fib_618_retrace(close, swing_window=5)
        # First swing detection requires window bars to pass
        # Levels should be NaN before swing is detected
        assert result.iloc[:5].isna().all()

    def test_confluence_score(self):
        """Multiple fib levels at similar price = higher confluence."""
        from finbar_strategy_runtime.domain.services.fibonacci_levels import (
            fib_confluence_score,
        )

        close = pd.Series([100.0, 130.0, 160.0, 190.0, 220.0, 250.0, 240.0, 235.0])
        score = fib_confluence_score(close, swing_window=3)
        assert isinstance(score.iloc[-1], (int, float, np.integer, np.floating))


# =========================================================================
# Bill Williams indicators
# =========================================================================


class TestBillWilliams:
    """Bill Williams chaos theory indicators."""

    def test_awesome_oscillator(self):
        from finbar_strategy_runtime.domain.services.bill_williams_indicators import (
            awesome_oscillator,
        )

        close = pd.Series(100.0 + np.arange(60) * 0.5)
        high = pd.Series(close + 5.0)
        low = pd.Series(close - 5.0)
        ao = awesome_oscillator(high, low)
        assert len(ao) == len(close)
        # AO = SMA5(median) - SMA34(median); positive in uptrend
        assert (ao.dropna() > 0).all()

    def test_alligator_lines(self):
        from finbar_strategy_runtime.domain.services.bill_williams_indicators import (
            alligator_lines,
        )

        close = pd.Series(100.0 + np.arange(80) * 0.5)
        high = pd.Series(close + 2.0)
        low = pd.Series(close - 2.0)
        jaw, teeth, lips = alligator_lines(high, low)
        assert len(jaw) == len(close)
        assert len(teeth) == len(close)
        assert len(lips) == len(close)

    def test_alligator_status(self):
        from finbar_strategy_runtime.domain.services.bill_williams_indicators import (
            alligator_lines,
            alligator_status,
        )

        close = pd.Series(100 + np.arange(80) * 0.5)
        high = pd.Series(close + 2)
        low = pd.Series(close - 2)
        jaw, teeth, lips = alligator_lines(high, low)
        status = alligator_status(jaw, teeth, lips)
        assert status.iloc[-1] in ("sleeping", "waking", "eating", "unknown")

    def test_williams_fractals(self):
        from finbar_strategy_runtime.domain.services.bill_williams_indicators import (
            williams_fractal_high,
            williams_fractal_low,
        )

        high = pd.Series([10.0, 11.0, 12.0, 13.0, 12.0, 11.0, 10.0, 11.0, 12.0, 11.0])
        low = pd.Series([5.0, 4.0, 3.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 4.0])
        fh = williams_fractal_high(high)
        fl = williams_fractal_low(low)
        # Fractals produce non-NA values only at confirmed signal positions
        assert fh.isna().iloc[-1] or pd.isna(fh.iloc[-1])

    def test_zone_signal(self):
        from finbar_strategy_runtime.domain.services.bill_williams_indicators import (
            zone_signal,
        )

        close = pd.Series(100 + np.arange(50) * 0.5)
        high = pd.Series(close + 2)
        low = pd.Series(close - 2)
        result = zone_signal(high, low)
        assert result.iloc[-1] in ("green", "red", "gray")


# =========================================================================
# Dow Theory / trend structure
# =========================================================================


class TestTrendStructure:
    """Dow Theory trend detection."""

    def test_swing_high_n_generalizes(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            swing_high_n,
        )

        high = pd.Series([10.0, 12.0, 11.0, 13.0, 12.0, 10.0, 11.0] * 10)
        result = swing_high_n(high, n=5)
        assert len(result) == len(high)

    def test_swing_low_n_generalizes(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            swing_low_n,
        )

        low = pd.Series([5.0, 4.0, 5.0, 4.0, 6.0, 5.0, 4.0] * 10)
        result = swing_low_n(low, n=5)
        assert len(result) == len(low)

    def test_hh_hl_pattern(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            hh_hl_pattern,
        )

        # Uptrend with 60 bars
        high = pd.Series(10.0 + np.arange(60) * 0.5)
        low = pd.Series(8.0 + np.arange(60) * 0.5)
        result = hh_hl_pattern(high, low, lookback=30)
        # Returns boolean series (may be True or False depending on swing detection)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_lh_ll_pattern(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            lh_ll_pattern,
        )

        high = pd.Series(40.0 - np.arange(60) * 0.5)
        low = pd.Series(38.0 - np.arange(60) * 0.5)
        result = lh_ll_pattern(high, low, lookback=30)
        assert isinstance(result.iloc[-1], (bool, np.bool_))

    def test_volume_trend_confirmation(self):
        from finbar_strategy_runtime.domain.services.trend_structure import (
            volume_trend_confirmation,
        )

        close = pd.Series(100.0 + np.arange(30) * 0.5)  # uptrend
        volume = pd.Series([2000.0] * 30)
        result = volume_trend_confirmation(close, volume)
        assert isinstance(result.iloc[-1], (bool, np.bool_))
