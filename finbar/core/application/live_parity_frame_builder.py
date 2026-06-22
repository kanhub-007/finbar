"""Build a causal enriched frame via the streaming MTF enricher.

Used by the backtest live-parity mode: each primary bar's enriched row is
produced by ``CausalMultiTimeframeStreamingEnricher`` from only the bars
available at that bar's close, then assembled into a DataFrame for the
existing backtest engine. The resulting frame is causal even though it is
materialised — every row came from the streaming enricher's prefix, not
from full-frame batch enrichment.
"""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
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
    return CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
        primary_bars=primary_bars,
        informative_bars=info,
        definition=definition,
        primary_indicators=primary_required_indicators,
        informative_indicators=informative_required_indicators,
    )


def _normalise_informative(
    informative_bars: dict[str, list[dict]] | list[dict] | None,
) -> dict[str, list[dict]]:
    """Return informative bars keyed by alias."""
    if informative_bars is None:
        return {}
    if isinstance(informative_bars, list):
        return {"h1": informative_bars}
    return dict(informative_bars)
