"""PandasTimeframeBarMerger — pandas implementation of timeframe merging."""

from typing import Any

from finbar.core.domain.interfaces.timeframe_bar_merger import TimeframeBarMerger
from finbar.infrastructure.services.bar_merger import merge_timeframes


class PandasTimeframeBarMerger(TimeframeBarMerger):
    """Merge informative pandas DataFrame columns into primary bars."""

    def merge(
        self,
        primary: Any,
        informative: Any,
        informative_interval: str,
        columns: list[str] | None = None,
    ) -> Any:
        """Return primary frame enriched with suffixed informative columns."""
        return merge_timeframes(primary, informative, informative_interval, columns)
