"""Contract tests for StrategyIndicatorCatalog — Scenario 4b (Slice 1).

Verifies the legacy catalog's rolling-VP pattern resolution: names of
the form ``vp_*_Nd``, ``rvp_*_N``, ``cvp_*_Nd`` (with window ``>= 1``)
must resolve to themselves via ``resolve()``, agreeing with
``supports_concrete()``. This closes the resolve/supports_concrete
asymmetry that previously rejected any window not hardcoded in
``_FIXED`` (e.g. ``vp_poc_10d``, ``rvp_poc_100``, ``cvp_poc_50d``).

Classical school: real catalog instance, outcome-based assertions.
"""

import pytest

from finbar_strategy_runtime.parser.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)


@pytest.fixture
def catalog() -> StrategyIndicatorCatalog:
    """Build the legacy StrategyIndicatorCatalog."""
    return StrategyIndicatorCatalog()


class TestRollingVpPatternResolution:
    """resolve() must accept every rolling-VP window >= 1, not just _FIXED."""

    # Windows NOT in _FIXED — these were the broken ones (returned None).
    @pytest.mark.parametrize(
        "name",
        [
            # vp_*_Nd — only 5d/20d are in _FIXED
            "vp_poc_10d",
            "vp_vah_50d",
            "vp_val_100d",
            # rvp_*_N — only 48/96/336 are in _FIXED
            "rvp_poc_100",
            "rvp_vah_200",
            "rvp_val_500",
            # cvp_*_Nd — only 5d/10d/20d are in _FIXED
            "cvp_poc_50d",
            "cvp_vah_100d",
            "cvp_val_3d",
        ],
    )
    def test_non_hardcoded_window_resolves(self, catalog, name):
        assert catalog.resolve(name, None) == name

    # Windows already in _FIXED — must still resolve (no regression).
    @pytest.mark.parametrize(
        "name",
        ["vp_poc_5d", "vp_vah_20d", "rvp_vah_48", "cvp_val_20d"],
    )
    def test_hardcoded_window_still_resolves(self, catalog, name):
        assert catalog.resolve(name, None) == name

    @pytest.mark.parametrize(
        "name",
        [
            "vp_poc_10d",
            "rvp_poc_100",
            "cvp_poc_50d",
            "vp_vah_5d",
            "rvp_vah_48",
            "cvp_vah_20d",
            # Window=1: the ``_Nd`` window suffix collides with the ``_1d``
            # timeframe suffix that supports_concrete() strips first.
            # Regression for the cvp_*_1d asymmetry bug.
            "cvp_poc_1d",
            "cvp_vah_1d",
            "cvp_val_1d",
        ],
    )
    def test_resolve_and_supports_concrete_agree(self, catalog, name):
        """resolve() and supports_concrete() must be symmetric for patterns."""
        assert (catalog.resolve(name, None) is not None) == catalog.supports_concrete(
            name
        )


class TestRollingVpPatternRejection:
    """Invalid windows / malformed patterns are rejected."""

    @pytest.mark.parametrize(
        "name",
        ["vp_poc_0d", "rvp_poc_0", "cvp_poc_0d"],
    )
    def test_zero_window_rejected(self, catalog, name):
        assert catalog.resolve(name, None) is None

    @pytest.mark.parametrize(
        "name",
        ["vp_poc_xd", "rvp_poc_abc", "cvp_poc_xd", "vp_poc_d"],
    )
    def test_non_numeric_window_rejected(self, catalog, name):
        assert catalog.resolve(name, None) is None
