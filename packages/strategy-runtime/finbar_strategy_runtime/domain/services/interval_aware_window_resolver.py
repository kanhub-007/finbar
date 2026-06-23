"""IntervalAwareWindowResolver — session-count windows from interval context.

Replaces the hardcoded 500-bar session-count window. For session-count
metrics (``poc_slope_N``, ``wyckoff_phase``, ``value_area_migration``) it
computes ``lookback_sessions × bars_per_session`` using the actual interval
and market calendar, so e.g. ``poc_slope_20`` on 30min crypto gets 960
bars instead of the too-short 500.

Non-session metrics return ``None`` so the engine keeps its existing
catalog/min-lookback resolution for them.
"""

from __future__ import annotations

import re

from finbar_strategy_runtime.domain.entities.interval_context import (
    IntervalContext,
)

_POC_SLOPE_RE = re.compile(r"^poc_slope_(\d+)$")
#: Session-count metrics that are not parameterised in their name.
_FIXED_SESSION_METRICS = {
    "wyckoff_phase": 20,  # uses poc_slope_20 internally
    "value_area_migration": 1,  # needs previous-session context
}

#: Floor for resolved windows so a tiny lookback never underflows buffers.
_MIN_WINDOW = 10


class IntervalAwareWindowResolver:
    """Resolve session-count streaming windows from interval context."""

    def __init__(
        self,
        interval: str = "",
        market_calendar: str = "crypto_24_7",
        context: IntervalContext | None = None,
    ) -> None:
        """Create the resolver from interval + market calendar.

        Args:
            interval: Bar interval (e.g. ``"30min"``, ``"1h"``).
            market_calendar: ``"crypto_24_7"`` or ``"equity_regular_hours"``.
            context: Optional pre-built :class:`IntervalContext`; takes
                precedence over ``interval``/``market_calendar``.
        """
        self._context = context or IntervalContext(
            interval=interval, market_calendar=market_calendar
        )

    @property
    def context(self) -> IntervalContext:
        """The interval context this resolver uses."""
        return self._context

    def resolve(self, metric_name: str) -> int | None:
        """Return the session-count window for *metric_name*, or None.

        Args:
            metric_name: Concrete metric name.

        Returns:
            Window size in bars for session-count metrics, else ``None``
            (caller falls back to its default resolution).

        Raises:
            ValueError: For session-count metrics when the interval cannot
                resolve bars-per-session (unknown interval / calendar), so
                the engine never silently uses a wrong fixed window.
        """
        lookback_sessions = _lookback_sessions(metric_name)
        if lookback_sessions is None:
            return None
        bars_per_session = self._context.bars_per_session
        return max(lookback_sessions * bars_per_session, _MIN_WINDOW)


def _lookback_sessions(metric_name: str) -> int | None:
    """Return the session lookback for a metric, or None if not session-count."""
    match = _POC_SLOPE_RE.match(metric_name)
    if match is not None:
        return int(match.group(1))
    if metric_name in _FIXED_SESSION_METRICS:
        return _FIXED_SESSION_METRICS[metric_name]
    return None


__all__ = ["IntervalAwareWindowResolver"]
