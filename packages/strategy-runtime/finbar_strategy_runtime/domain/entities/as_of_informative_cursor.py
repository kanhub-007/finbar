"""AsOfInformativeCursor — causal, O(n+m) as-of informative lookup.

One cursor per informative timeframe alias. It stores informative rows
keyed by their *availability* timestamp (open + interval offset) and
advances a monotonic pointer as primary bar timestamps increase.

Because primary opens are monotonically increasing, the pointer never
moves backward: each :meth:`latest_visible_at` call advances it at most
a few steps, giving O(primary + informative) total cost instead of the
O(primary × informative) reverse-scan it replaces.

The cursor enforces no-lookahead: an informative bar is visible only once
it has fully closed, i.e. ``availability_timestamp <= primary_open``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class AsOfInformativeCursor:
    """Monotonic-pointer as-of lookup over informative availability timestamps.

    Attributes:
        offset: Interval offset added to each bar's open timestamp to get its
            availability (close) timestamp. Defaults to zero (bar visible at
            its own open).
        availability_timestamps: Ordered availability timestamps (open+offset).
        rows: Informative row dicts, parallel to ``availability_timestamps``.
        position: Index of the last row made visible by a lookup. ``-1`` means
            no row has become visible yet.
    """

    offset: pd.Timedelta = field(default_factory=lambda: pd.Timedelta(0))
    availability_timestamps: list[pd.Timestamp] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    position: int = -1

    def append(self, open_ts: pd.Timestamp, row: dict) -> None:
        """Append an informative bar.

        Args:
            open_ts: The bar's open timestamp; its availability is
                ``open_ts + offset``.
            row: The enriched informative row dict to expose on lookup.

        Raises:
            ValueError: If the bar's availability precedes the last appended
                one (timestamps must be monotonic to keep the pointer valid).
        """
        availability = open_ts + self.offset
        timestamps = self.availability_timestamps
        last = timestamps[-1] if timestamps else None
        if last is not None and availability < last:
            raise ValueError(
                "AsOfInformativeCursor requires monotonically increasing "
                "availability timestamps."
            )
        self.availability_timestamps.append(availability)
        self.rows.append(row)

    def latest_visible_at(self, primary_open: pd.Timestamp) -> dict | None:
        """Return the latest row whose availability is at or before *primary_open*.

        Advances the internal pointer while subsequent rows have become
        visible. Because primary opens are monotonic, this is O(1) amortised.

        Returns:
            The latest visible row dict, or None if no bar is visible yet.
        """
        i = self.position
        while i + 1 < len(self.availability_timestamps) and (
            self.availability_timestamps[i + 1] <= primary_open
        ):
            i += 1
        self.position = i
        if i < 0:
            return None
        return self.rows[i]

    def reset(self) -> None:
        """Clear all appended rows and reset the pointer."""
        self.availability_timestamps.clear()
        self.rows.clear()
        self.position = -1


__all__ = ["AsOfInformativeCursor"]
