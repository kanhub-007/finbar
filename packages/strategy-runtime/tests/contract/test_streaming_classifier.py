"""Contract tests for the streaming indicator classifier.

Verifies that classify_indicator() resolves every registered handler name
to STREAMING or WINDOWED (never UNKNOWN) and that genuinely unknown names
fail closed.
"""

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _collect_all_handler_names():
    """Return the set of all registered handler names (static + dynamic-checked)."""
    from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
        _INDICATOR_HANDLERS,
    )

    return set(_INDICATOR_HANDLERS.keys())


def _is_dynamic(name: str) -> bool:
    """Check whether name matches a dynamic-pattern (sma_N, ema_N, etc.)."""
    from finbar_strategy_runtime.indicators._dynamic_dispatch import (
        _is_dynamic,
    )

    return _is_dynamic(name)


def _is_rolling_vp(name: str) -> bool:
    """Check whether name matches a rolling-VP pattern."""
    from finbar_strategy_runtime.indicators._dynamic_dispatch import (
        _is_rolling_vp,
    )

    return _is_rolling_vp(name)


# ── Test helpers ─────────────────────────────────────────────────────────────

_HAND_NAMED_STREAMING = frozenset(
    {
        "sma_10",
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_26",
        "rsi_7",
        "rsi_14",
        "atr",
        "adx",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "ker",
        "kama",
        "vwap",
        "ibs",
        "rvol",
    }
)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestIndicatorKindEnum:
    def test_kind_values(self):
        """IndicatorKind has STREAMING, WINDOWED, UNKNOWN."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            IndicatorKind,
        )

        assert IndicatorKind.STREAMING.value == "STREAMING"
        assert IndicatorKind.WINDOWED.value == "WINDOWED"
        assert IndicatorKind.UNKNOWN.value == "UNKNOWN"


class TestUnsupportedStreamingIndicatorError:
    def test_is_value_error(self):
        """UnsupportedStreamingIndicatorError is a ValueError."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            UnsupportedStreamingIndicatorError,
        )

        with pytest.raises(ValueError):
            raise UnsupportedStreamingIndicatorError("typo_metric")


class TestClassifyIndicator:
    """Black-box tests for classify_indicator()."""

    def test_hand_listed_streaming(self):
        """Hand-listed names (sma_20, rsi_14, macd, etc.) → STREAMING."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            IndicatorKind,
            classify_indicator,
        )

        for name in _HAND_NAMED_STREAMING:
            kind = classify_indicator(name)
            assert kind == IndicatorKind.STREAMING, (
                f"{name} classified as {kind}, expected STREAMING"
            )

    def test_dynamic_period_streaming(self):
        """Dynamic-period names (sma_37, ema_21, rsi_21, etc.) → STREAMING."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            IndicatorKind,
            classify_indicator,
        )

        dynamics = [
            "sma_37",
            "ema_21",
            "rsi_21",
            "atr_7",
            "adx_7",
            "bb_upper_20",
            "bb_middle_10",
            "bb_lower_15",
        ]
        for name in dynamics:
            kind = classify_indicator(name)
            assert kind == IndicatorKind.STREAMING, (
                f"{name} classified as {kind}, expected STREAMING"
            )

    def test_vp_prefix_windowed(self):
        """VP-prefix names (rvp_poc_48, vp_poc_10d, cvp_poc_5d) → WINDOWED."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            IndicatorKind,
            classify_indicator,
        )

        vp_names = [
            "rvp_poc_48",
            "rvp_vah_48",
            "rvp_val_48",
            "vp_poc_10d",
            "vp_vah_10d",
            "vp_val_10d",
            "cvp_poc_5d",
            "cvp_vah_5d",
        ]
        for name in vp_names:
            kind = classify_indicator(name)
            assert kind == IndicatorKind.WINDOWED, (
                f"{name} classified as {kind}, expected WINDOWED"
            )

    @pytest.mark.parametrize(
        "indicator",
        [
            "bearish_fvg",
            "demand_zone_score",
            "roll_spread",
            "awesome_oscillator",
            "hurst_exponent",
        ],
    )
    def test_windowed_default_representatives(self, indicator):
        """Representative windowed-default indicators → WINDOWED, not raise."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            IndicatorKind,
            classify_indicator,
        )

        kind = classify_indicator(indicator)
        assert kind == IndicatorKind.WINDOWED, (
            f"{indicator} classified as {kind}, expected WINDOWED"
        )

    def test_unknown_name_raises(self):
        """A genuinely unknown name → UNKNOWN and raises error."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            UnsupportedStreamingIndicatorError,
        )

        with pytest.raises(UnsupportedStreamingIndicatorError):
            # Must raise because _streaming_classifier enforces fail-closed
            # on unknown names
            from finbar_strategy_runtime.indicators._streaming_classifier import (
                classify_indicator,
            )

            classify_indicator("typo_metric")


class TestAdoptabilityGuard:
    """Every registered handler name must resolve to STREAMING or WINDOWED.

    This is the property that guarantees no live strategy crashes at
    engine construction due to a catalogued indicator.
    """

    @pytest.mark.parametrize(
        "name", sorted(_collect_all_handler_names())
    )
    def test_every_registered_handler_is_streamable(self, name):
        """Every handler name → STREAMING or WINDOWED, never UNKNOWN."""
        from finbar_strategy_runtime.indicators._streaming_classifier import (
            IndicatorKind,
            classify_indicator,
        )

        kind = classify_indicator(name)
        assert kind in (IndicatorKind.STREAMING, IndicatorKind.WINDOWED), (
            f"Registered handler '{name}' classified as {kind} — "
            f"must be STREAMING or WINDOWED (adoptability guard)"
        )
