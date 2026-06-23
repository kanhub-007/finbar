"""RollingVolumeProfileState — causal streaming state for RVP metrics."""

from __future__ import annotations

import math

from finbar_strategy_runtime.domain.services.volume_profile import (
    compute_rolling_window_vp,
)
from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)

_RVP_PREFIXES = ("rvp_poc_", "rvp_vah_", "rvp_val_")


class RollingVolumeProfileState(StreamingIndicatorState):
    """Causal prefix state for rolling-window volume-profile metrics.

    The state stores the causal prefix of bars seen so far and computes the
    latest RVP value from ``compute_rolling_window_vp(prefix, window)``. This is
    correctness-first and intentionally mirrors the prefix oracle; a later
    optimization can replace the full-prefix recompute with an incremental
    ring-buffer implementation without changing public semantics.
    """

    def __init__(self, name: str) -> None:
        """Initialise the state for one RVP metric name.

        Args:
            name: RVP metric name, e.g. ``rvp_poc_48``.

        Raises:
            ValueError: If the metric name is not a supported RVP name.
        """
        self._name = name
        self._window_bars = _parse_window_bars(name)
        self._bars: list[dict] = []
        self._current = math.nan
        self._converter = PandasBarFrameConverter()

    def update(self, bar: dict) -> float:
        """Ingest one bar and return the latest RVP value."""
        self._bars.append(bar)
        if len(self._bars) < self._window_bars:
            self._current = math.nan
            return self._current
        frame = self._converter.bars_to_frame(self._bars)
        result = compute_rolling_window_vp(frame, window_bars=self._window_bars)
        self._current = float(result[self._name].iloc[-1])
        return self._current

    def reset(self) -> None:
        """Clear accumulated prefix state."""
        self._bars.clear()
        self._current = math.nan

    @property
    def value(self) -> float:
        """Most recently computed RVP value."""
        return self._current


def _parse_window_bars(name: str) -> int:
    """Parse the trailing bar count from an RVP metric name."""
    for prefix in _RVP_PREFIXES:
        if name.startswith(prefix):
            value = name[len(prefix) :]
            if value.isdigit() and int(value) >= 1:
                return int(value)
    raise ValueError(f"Unsupported rolling volume profile metric: {name}")


def is_rolling_volume_profile_metric(name: str) -> bool:
    """Return True when a name is an RVP metric."""
    try:
        _parse_window_bars(name)
    except ValueError:
        return False
    return True
