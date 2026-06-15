"""Regression tests for optimizer random-search helpers."""

from finbar.core.domain.entities.param_range import ParamRange
from finbar.infrastructure.services.grid_search_optimizer import (
    _generate_random_combinations,
)


class TestRandomCombinationGeneration:
    def test_random_search_stops_when_requested_count_exceeds_unique_grid(self):
        """Random search must not hang when only one unique combo exists."""
        ranges = {"fast_period": ParamRange(min=10, max=10, step=1)}

        result = _generate_random_combinations(ranges, count=20)

        assert result == [{"fast_period": 10}]

    def test_random_search_values_stay_inside_declared_range(self):
        ranges = {"threshold": ParamRange(min=0.0, max=1.0, step=0.6)}

        result = _generate_random_combinations(ranges, count=20)

        assert result
        assert all(0.0 <= item["threshold"] <= 1.0 for item in result)
