"""Contract tests for the StreamingIndicatorCalculator interface and LatestBar VO.

Verifies that the ABC enforces abstract methods and that LatestBar is a
plain value object with the expected fields.
"""

import pytest


class TestStreamingIndicatorCalculatorInterface:
    """Black-box tests for the StreamingIndicatorCalculator ABC."""

    def test_cannot_instantiate_without_concrete_methods(self):
        """The ABC cannot be instantiated — all methods are abstract."""
        from finbar_strategy_runtime.domain.interfaces.streaming_indicator_calculator import (
            StreamingIndicatorCalculator,
        )

        with pytest.raises(
            TypeError,
            match="abstract.*(update|latest|is_ready|reset)",
        ):
            StreamingIndicatorCalculator()  # type: ignore[abstract]

    def test_abstract_methods_defined(self):
        """All four abstract methods are declared on the ABC."""

        from finbar_strategy_runtime.domain.interfaces.streaming_indicator_calculator import (
            StreamingIndicatorCalculator,
        )

        assert hasattr(StreamingIndicatorCalculator, "update")
        assert hasattr(StreamingIndicatorCalculator, "latest")
        assert hasattr(StreamingIndicatorCalculator, "is_ready")
        assert hasattr(StreamingIndicatorCalculator, "reset")

        # Confirm they are abstract
        for name in ("update", "latest", "is_ready", "reset"):
            method = getattr(StreamingIndicatorCalculator, name)
            assert hasattr(method, "__isabstractmethod__"), (
                f"{name} is not abstract"
            )


class TestLatestBar:
    """Black-box tests for the LatestBar value object."""

    def test_construct_with_values(self):
        """LatestBar holds values, is_ready, and bars_seen."""
        from finbar_strategy_runtime.domain.entities.latest_bar import (
            LatestBar,
        )

        bar = LatestBar(
            values={"sma_20": 100.5, "rsi_14": 55.0},
            is_ready=True,
            bars_seen=25,
        )
        assert bar.values == {"sma_20": 100.5, "rsi_14": 55.0}
        assert bar.is_ready is True
        assert bar.bars_seen == 25

    def test_construct_empty(self):
        """Default construction: empty values, not ready, zero bars."""
        from finbar_strategy_runtime.domain.entities.latest_bar import (
            LatestBar,
        )

        bar = LatestBar()
        assert bar.values == {}
        assert bar.is_ready is False
        assert bar.bars_seen == 0

    def test_immutable(self):
        """LatestBar is a frozen dataclass — cannot reassign attributes."""
        from dataclasses import FrozenInstanceError

        from finbar_strategy_runtime.domain.entities.latest_bar import (
            LatestBar,
        )

        bar = LatestBar(values={"a": 1.0})
        with pytest.raises(FrozenInstanceError):
            bar.values = {"b": 2.0}  # type: ignore[misc]
