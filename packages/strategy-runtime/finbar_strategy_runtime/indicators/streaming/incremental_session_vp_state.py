"""IncrementalSessionVpState — expanding session Volume Profile, O(session) per bar.

Buffers the current session's bars and recomputes POC/VAH/VAL on each
update using ``compute_session_volume_profile`` — the identical algorithm
as the batch handler. On session boundary the buffer resets.

Values match the batch-prefix oracle exactly because both use the same
Gaussian volume distribution model (Parkinson sigma, 100 buckets, 68% VA).

Per-bar cost is O(session_bars_so_far) — much cheaper than O(window=500)
for the full windowed recompute, and identical to the existing
``compute_expanding_session_volume_profiles`` definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from finbar_strategy_runtime.domain.services.volume_profile import (
    compute_session_volume_profile,
)
from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_state import (
    StreamingIndicatorState,
)


@dataclass(frozen=True)
class _VpLevels:
    poc: float
    vah: float
    val: float


class IncrementalSessionVpState(StreamingIndicatorState):
    """Expanding session VP using the identical batch handler algorithm.

    Maintains a growing buffer of the current session's bars. On each bar,
    calls ``compute_session_volume_profile`` on the prefix — this is the
    same function the batch handler uses, guaranteeing exact parity.
    """

    def __init__(self) -> None:
        self._bars: list[dict] = []
        self._session_date: str | None = None
        self._last_levels: _VpLevels | None = None

    # ── public ──────────────────────────────────────────────────────────

    def update(self, bar: dict) -> None:
        """Ingest one bar; recompute VP on the expanding session prefix.

        Resets the buffer on session boundary.
        """
        ts = bar.get("timestamp")
        if ts is not None:
            bar_date = _session_date(ts)
            if self._session_date is not None and bar_date != self._session_date:
                self.reset()
            self._session_date = bar_date

        self._bars.append(bar)
        self._last_levels = None  # invalidate
        self._recompute()

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

    def reset(self) -> None:
        self._bars.clear()
        self._last_levels = None

    # ── internal ────────────────────────────────────────────────────────

    def _ensure(self) -> None:
        if self._last_levels is None and self._bars:
            self._recompute()

    def _recompute(self) -> None:
        if len(self._bars) < 1:
            self._last_levels = None
            return
        frame = self._to_frame()
        profile = compute_session_volume_profile(frame, num_buckets=100)
        self._last_levels = _VpLevels(
            poc=float(profile.poc),
            vah=float(profile.vah),
            val=float(profile.val),
        )

    def _to_frame(self) -> pd.DataFrame:
        timestamps = [bar["timestamp"] for bar in self._bars]
        index = parse_bar_timestamps(timestamps)
        return pd.DataFrame(self._bars, index=index)


def _session_date(timestamp: Any) -> str:
    return parse_bar_timestamps([timestamp])[0].date().isoformat()
