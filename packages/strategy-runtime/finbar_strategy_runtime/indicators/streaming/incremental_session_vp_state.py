"""IncrementalSessionVpState — expanding session Volume Profile, O(buckets) per bar.

Buffers the current session's bars and incrementally maintains the volume
profile. Instead of recomputing from scratch on every bar (O(session_bars²)),
each update only distributes the NEW bar's volume across the price buckets
and adds it to the running profile — O(buckets).

The full profile is rebuilt (redistribute all bars) only when the session
range expands beyond the existing bucket grid. In practice this happens on
the first few bars of a session; subsequent bars rarely extend the range.

Values match the batch-prefix oracle exactly because both use the same
Gaussian volume distribution model (Parkinson sigma, 100 buckets, 68% VA).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from finbar_strategy_runtime.domain.services.volume_profile import (
    _build_volume_profile_result,
    _session_bucket_grid,
    _distribute_bar_volume,
)
from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)

_NUM_BUCKETS = 100


@dataclass(frozen=True)
class _VpLevels:
    poc: float
    vah: float
    val: float


class IncrementalSessionVpState(StreamingIndicatorState):
    """Expanding session VP with incremental volume accumulation.

    Maintains a running volume profile array and total volume. Each bar
    adds its distributed volume to the running profile rather than
    recomputing all bars from scratch. The bucket grid is rebuilt only
    when the session range expands beyond the grid boundaries.
    """

    def __init__(self) -> None:
        self._bars: list[dict] = []
        self._session_date: str | None = None
        self._last_levels: _VpLevels | None = None
        # Incremental state
        self._volume_profile: np.ndarray | None = None
        self._total_volume: float = 0.0
        self._price_buckets: np.ndarray | None = None
        self._bucket_size: float = 0.0
        self._session_high: float = 0.0
        self._session_low: float = 0.0
        # Session-end POC history for slope computation.
        # Each entry is (session_date_str, final_poc). Max 21 entries
        # covers poc_slope_20.
        from collections import deque as _deque
        self._session_pocs: _deque[tuple[str, float]] = _deque(maxlen=21)

    # ── public ──────────────────────────────────────────────────────────

    def update(self, bar: dict) -> None:
        """Ingest one bar; incrementally update the volume profile.

        Resets the buffer and cached profile on session boundary.
        Captures the previous session's final POC for slope computation.
        """
        ts = bar.get("timestamp")
        if ts is not None:
            bar_date = _session_date(ts)
            if self._session_date is not None and bar_date != self._session_date:
                # Cap previous session: save its final POC before reset.
                self._cap_session()
                self.reset()
            self._session_date = bar_date

        self._bars.append(bar)
        self._last_levels = None  # invalidate
        self._update_incremental(bar)

    @property
    def poc(self) -> float:
        self._ensure()
        return self._last_levels.poc if self._last_levels else float("nan")

    @property
    def vah(self) -> float:
        self._ensure()
        return self._last_levels.vah if self._last_levels else float("nan")

    @property
    def val(self) -> float:
        self._ensure()
        return self._last_levels.val if self._last_levels else float("nan")

    @property
    def value(self) -> float:
        return self.poc

    def poc_slope(self, n_sessions: int = 5) -> float:
        """POC % change over the last *n_sessions* calendar days.

        Returns NaN when fewer than *n_sessions* of session-end POC
        history have been accumulated.
        """
        if len(self._session_pocs) < max(n_sessions, 1):
            return float("nan")
        older_poc = self._session_pocs[-n_sessions][1]
        newer_poc = self._session_pocs[-1][1]
        if older_poc <= 0:
            return float("nan")
        return (newer_poc - older_poc) / older_poc * 100.0

    def reset(self) -> None:
        self._bars.clear()
        self._last_levels = None
        self._volume_profile = None
        self._total_volume = 0.0
        self._price_buckets = None
        self._bucket_size = 0.0
        self._session_high = 0.0
        self._session_low = 0.0
        # Note: _session_pocs is NOT cleared — it holds historical
        # session-end POCs needed for poc_slope computation across
        # multiple sessions.

    # ── internal ────────────────────────────────────────────────────────

    def _cap_session(self) -> None:
        """Save the current session's final POC into the history deque."""
        self._ensure()
        if self._last_levels is not None and self._session_date is not None:
            self._session_pocs.append(
                (self._session_date, self._last_levels.poc)
            )

    def _ensure(self) -> None:
        if self._last_levels is None and self._bars:
            self._extract_levels()

    def _update_incremental(self, bar: dict) -> None:
        """Add one bar's volume to the running profile.

        Builds the initial bucket grid on the first bar. Rebuilds the
        full profile when the session range expands beyond the grid.
        """
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        bar_close = float(bar["close"])
        bar_volume = float(bar["volume"])

        if self._price_buckets is None:
            # First bar of session — build the initial grid
            self._session_high = bar_high
            self._session_low = bar_low
            self._price_buckets, self._bucket_size = _session_bucket_grid(
                bar_high, bar_low, _NUM_BUCKETS
            )
            self._volume_profile = np.zeros(_NUM_BUCKETS)
            self._total_volume = 0.0
        elif bar_high > self._session_high or bar_low < self._session_low:
            # Session range expanded — rebuild the full profile once.
            # This is rare: only the first few bars of a session
            # typically extend the range.
            self._session_high = max(self._session_high, bar_high)
            self._session_low = min(self._session_low, bar_low)
            self._price_buckets, self._bucket_size = _session_bucket_grid(
                self._session_high, self._session_low, _NUM_BUCKETS
            )
            # Redistribute all bars into the new grid
            self._volume_profile = np.zeros(_NUM_BUCKETS)
            self._total_volume = 0.0
            self._redistribute_all()
            return

        # Common case: add this bar's volume to the running profile
        self._add_bar(bar_high, bar_low, bar_close, bar_volume)

    def _add_bar(
        self, bar_high: float, bar_low: float, bar_close: float, bar_volume: float
    ) -> None:
        """Distribute one bar's volume and add to the running profile."""
        if bar_volume <= 0 or self._bucket_size <= 0:
            return
        distributed = _distribute_bar_volume(
            bar_high, bar_low, bar_close, bar_volume,
            self._price_buckets, self._bucket_size,
        )
        self._volume_profile += distributed
        self._total_volume += bar_volume

    def _redistribute_all(self) -> None:
        """Rebuild the profile by distributing ALL bars in the session.

        Only called on grid rebuild (session range expansion).
        """
        for bar in self._bars:
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            bar_close = float(bar["close"])
            bar_volume = float(bar["volume"])
            self._add_bar(bar_high, bar_low, bar_close, bar_volume)

    def _extract_levels(self) -> None:
        """Extract POC/VAH/VAL from the running profile."""
        if self._volume_profile is None or self._total_volume <= 0:
            self._last_levels = None
            return
        result = _build_volume_profile_result(
            volume_profile=self._volume_profile,
            price_buckets=self._price_buckets,
            bucket_size=self._bucket_size,
            total_volume=self._total_volume,
            num_buckets=_NUM_BUCKETS,
        )
        self._last_levels = _VpLevels(
            poc=float(result.poc),
            vah=float(result.vah),
            val=float(result.val),
        )


def _session_date(timestamp: Any) -> str:
    return parse_bar_timestamps([timestamp])[0].date().isoformat()
