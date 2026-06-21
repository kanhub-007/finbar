"""Build a causal enriched frame via the streaming MTF enricher.

Used by the backtest live-parity mode: each primary bar's enriched row is
produced by ``CausalMultiTimeframeStreamingEnricher`` from only the bars
available at that bar's close, then assembled into a DataFrame for the
existing backtest engine. The resulting frame is causal even though it is
materialised — every row came from the streaming enricher's prefix, not
from full-frame batch enrichment.
"""

from __future__ import annotations

import pandas as pd
from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
)
from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)
from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (
    CausalMultiTimeframeStreamingEnricher,
)


def build_causal_frame(
    primary_bars: list[dict],
    informative_bars: dict[str, list[dict]] | list[dict] | None,
    definition: StrategyDefinition,
    primary_required_indicators: list[str],
    informative_required_indicators: dict[str, list[str]],
) -> pd.DataFrame:
    """Stream primary + informative bars through the causal enricher.

    Args:
        primary_bars: Primary OHLCV bar dicts sorted ascending by timestamp.
        informative_bars: Map from alias to OHLCV bar dicts (or flat list
            for a single informative).
        definition: Parsed strategy definition.
        primary_required_indicators: Primary indicator names.
        informative_required_indicators: Per-alias informative indicators.

    Returns:
        A DataFrame indexed by primary bar timestamp, with OHLCV, primary
        indicators, and suffixed merged informative columns — each row
        causal.
    """
    info = _normalise_informative(informative_bars)
    enricher = CausalMultiTimeframeStreamingEnricher(
        definition=definition,
        primary_indicators=primary_required_indicators,
        informative_indicators=informative_required_indicators,
    )

    info_ptrs = {alias: 0 for alias in info}
    rows: list[dict] = []
    for bar in primary_bars:
        primary_open = parse_bar_timestamps([bar["timestamp"]])[0]
        for alias, ibars in info.items():
            while info_ptrs[alias] < len(ibars):
                candidate = ibars[info_ptrs[alias]]
                if parse_bar_timestamps([candidate["timestamp"]])[0] <= primary_open:
                    enricher.update_informative(alias, candidate)
                    info_ptrs[alias] += 1
                else:
                    break
        rows.append(enricher.update_primary(bar).values)

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    ts = frame["timestamp"].tolist()
    index = parse_bar_timestamps(ts)
    return frame.drop(columns=["timestamp"]).set_index(index)


def _normalise_informative(
    informative_bars: dict[str, list[dict]] | list[dict] | None,
) -> dict[str, list[dict]]:
    """Return informative bars keyed by alias."""
    if informative_bars is None:
        return {}
    if isinstance(informative_bars, list):
        return {"h1": informative_bars}
    return dict(informative_bars)
