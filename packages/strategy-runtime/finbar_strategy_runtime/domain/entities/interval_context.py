"""IntervalContext — interval + market calendar semantics for streaming.

Carries the bar interval and market calendar so window resolvers and
metrics can derive interval-aware values (e.g. bars per session) instead
of hardcoding them. Pure value object — no I/O, no frameworks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INTERVAL_RE = re.compile(r"^(\d+)\s*(min|m|h|d|w)$", re.IGNORECASE)


@dataclass(frozen=True)
class IntervalContext:
    """Interval + market calendar context.

    Attributes:
        interval: Bar interval string (e.g. ``"30min"``, ``"1h"``).
        market_calendar: ``"crypto_24_7"`` or ``"equity_regular_hours"``.
    """

    interval: str
    market_calendar: str = "crypto_24_7"

    @property
    def bars_per_session(self) -> int:
        """Return the number of bars in one calendar session.

        A session is one calendar day for crypto (24h) and one regular
        trading day for equities (6.5h). Raises ``ValueError`` for an
        interval the context cannot resolve, so callers never silently fall
        back to a fixed bar count for session-count metrics.
        """
        normalized = (self.interval or "").lower().strip()
        match = _INTERVAL_RE.match(normalized)
        if match is None:
            raise ValueError(
                f"IntervalContext cannot resolve bars-per-session for "
                f"unknown interval {self.interval!r}."
            )
        amount = int(match.group(1))
        unit = match.group(2).lower()
        minutes_per_bar = _minutes(amount, unit)

        if self.market_calendar == "crypto_24_7":
            minutes_per_session = 24 * 60
        elif self.market_calendar == "equity_regular_hours":
            minutes_per_session = int(6.5 * 60)
        else:
            raise ValueError(
                f"IntervalContext cannot resolve bars-per-session for "
                f"unknown market calendar {self.market_calendar!r}."
            )

        if minutes_per_bar <= 0:
            raise ValueError(
                f"Interval {self.interval!r} yields non-positive bar length"
            )
        # Floor division: an interval that does not evenly divide a session
        # (e.g. 1h on a 6.5h equity day) gets a conservative floor. Session-
        # count windows use this as ``lookback_sessions x bars_per_session``,
        # so a slight underestimate of bars-per-session is a conservative
        # (slightly smaller) streaming window for warmup protection.
        return max(minutes_per_session // minutes_per_bar, 1)


def _minutes(amount: int, unit: str) -> int:
    if unit in ("min", "m"):
        return amount
    if unit == "h":
        return amount * 60
    if unit == "d":
        return amount * 24 * 60
    if unit == "w":
        return amount * 7 * 24 * 60
    raise ValueError(f"Unsupported interval unit: {unit!r}")


__all__ = ["IntervalContext"]
