"""DirectVpDerivedState — O(1) computation of VP-derived AMT metrics.

Instead of recomputing on a 500-bar window, maintains a small sliding
buffer sized to each metric's actual needs:
  - 1 bar  for single-row metrics (near_val, above_value, etc.)
  - 2 bars for shift-1 metrics (acceptance_into_value, etc.)
  - ~48 bars for session-scoped metrics (poc_slope_5 via incremental VP)

The batch handlers run unchanged on the micro-buffer, producing identical
results to the 500-bar path but at O(1) per bar.
"""

from __future__ import annotations

from collections import deque
from typing import Any

import pandas as pd

from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)

# ── buffer sizes per metric class ────────────────────────────────────────

_MICRO_WINDOW = 2    # for shift-1 metrics (acceptance_*)
_VOL_WINDOW = 20      # for volume-based metrics (stopping_volume, climax)


class DirectVpDerivedState:
    """Micro-window batch state for VP-derived AMT metrics.

    Each ``update()`` appends one bar, runs the registered batch
    handlers on the compact buffer, and captures the latest-row value
    for every requested metric.  POC-slope metrics are delegated to the
    incremental VP state's ``poc_slope()`` method.
    """

    def __init__(self, names: list[str], session_vp: Any) -> None:
        self._names = list(names)
        self._vp = session_vp
        self._values: dict[str, float | bool] = {}

        # Categorise metrics by needed buffer depth.
        self._micro_names: list[str] = []
        self._vol_names: list[str] = []
        self._slope_names: list[str] = []
        for n in self._names:
            if n in ("poc_slope_5", "poc_slope_20"):
                self._slope_names.append(n)
            elif n in ("stopping_volume", "climax_volume"):
                self._vol_names.append(n)
            else:
                self._micro_names.append(n)

        self._micro_buf: deque[dict] = deque(maxlen=_MICRO_WINDOW)
        self._vol_buf: deque[dict] = deque(maxlen=_VOL_WINDOW)

        # Reusable cached frame (rebuilt each update from the deques).
        self._frame: pd.DataFrame | None = None

    # ── public ──────────────────────────────────────────────────────────

    def update(self, bar: dict) -> None:
        """Compute all requested metrics from the micro-buffer."""
        self._micro_buf.append(bar)
        self._vol_buf.append(bar)

        for name in self._names:
            self._values[name] = float("nan")

        # POC slopes from incremental VP history (O(1))
        for name in self._slope_names:
            if name == "poc_slope_5":
                self._values[name] = self._vp.poc_slope(5)
            elif name == "poc_slope_20":
                self._values[name] = self._vp.poc_slope(20)

        # Micro-window batch (O(2))
        if self._micro_names:
            self._compute_batch(self._micro_names, self._micro_buf)

        # Volume-window batch (O(20))
        if self._vol_names:
            self._compute_batch(self._vol_names, self._vol_buf)

    @property
    def values(self) -> dict[str, float | bool]:
        return dict(self._values)

    def reset(self) -> None:
        self._micro_buf.clear()
        self._vol_buf.clear()
        self._frame = None

    # ── internal ────────────────────────────────────────────────────────

    def _compute_batch(
        self, names: list[str], buf: deque[dict]
    ) -> None:
        """Run batch handlers on *buf* and capture the last row's values."""
        if len(buf) < 2:
            return

        # Build frame with injected VP columns so handlers find them.
        ts = [b["timestamp"] for b in buf]
        index = parse_bar_timestamps(ts)
        frame = pd.DataFrame(list(buf), index=index)

        # Inject incremental VP columns (same values the 500-bar path uses).
        vp_poc_vals = [self._vp.poc] * len(frame)
        vp_vah_vals = [self._vp.vah] * len(frame)
        vp_val_vals = [self._vp.val] * len(frame)
        frame["vp_poc"] = vp_poc_vals
        frame["vp_vah"] = vp_vah_vals
        frame["vp_val"] = vp_val_vals

        # Run the registered batch handlers on the compact frame.
        from finbar_strategy_runtime.indicators._handler_registry import (
            default_handler_registry,
        )
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
            _expand_transitive_deps,
        )

        handlers = default_handler_registry()
        # Expand transitive deps, excluding VP roots (already injected).
        all_deps: set[str] = set()
        for name in names:
            if name in handlers:
                deps = [d for d in _expand_transitive_deps([name], handlers)
                        if d not in ("vp_poc", "vp_vah", "vp_val")]
                all_deps.update(d for d in deps if d in handlers)

        # Pre-compute dependencies.
        if all_deps:
            calc = PandasTaIndicatorCalculator()
            frame = calc.calculate(frame, list(all_deps))

        # Run each requested handler.
        from finbar_strategy_runtime.indicators._compute_decorators import (
            resolve_last_value_compute,
        )
        for name in names:
            compute = resolve_last_value_compute(name, handlers)
            if compute is not None:
                try:
                    val = compute(frame)
                    if val is not None and val == val:  # not NaN
                        self._values[name] = val
                except Exception:
                    pass
