"""CausalMultiTimeframeStreamingEnricher — stateful causal MTF enrichment.

Composes one ``StreamingIndicatorEngine`` per timeframe (scalar and
windowed indicators, already causal once real bar timestamps are
preserved) with an as-of informative merge that replicates the batch
merger's no-lookahead availability offset.

Per-bar cost is bounded by the largest windowed indicator window and the
current session length — it does NOT recompute over the full historical
prefix (ADR-5). The expanding current-session VP definition
(Scenario 4) is reproduced exactly because each windowed VP handler runs
on a bounded window that contains the full current session, so the
completed-so-far profile it broadcasts equals the expanding prefix at the
latest row.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from finbar_strategy_runtime.domain.entities.causal_enriched_bar import (
    CausalEnrichedBar,
)
from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
)
from finbar_strategy_runtime.domain.interfaces import (
    multi_timeframe_streaming_enricher as mtf_enricher_interface,
)
from finbar_strategy_runtime.indicators._bar_timestamp import (
    parse_bar_timestamps,
)
from finbar_strategy_runtime.indicators.bar_merger import interval_offset
from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
    StreamingIndicatorEngine,
)

_OHLCV = {"open", "high", "low", "close", "volume", "timestamp"}


class CausalMultiTimeframeStreamingEnricher(
    mtf_enricher_interface.MultiTimeframeStreamingEnricher
):
    """Incrementally enrich primary bars with informative context, causally."""

    def __init__(
        self,
        definition: StrategyDefinition,
        primary_indicators: list[str],
        informative_indicators: dict[str, list[str]],
    ) -> None:
        """Create the enricher from a parsed strategy definition.

        Args:
            definition: Parsed strategy definition whose ``.timeframes``
                carries each informative alias and interval.
            primary_indicators: Indicator names to compute on the primary
                timeframe.
            informative_indicators: Map from alias to indicator names to
                compute on each informative timeframe.
        """
        self._primary_engine = StreamingIndicatorEngine(indicators=primary_indicators)
        self._primary_indicators = list(primary_indicators)
        self._info_indicators = {
            alias: list(indicators)
            for alias, indicators in informative_indicators.items()
        }
        self._info_engines: dict[str, StreamingIndicatorEngine] = {}
        self._info_offsets: dict[str, pd.Timedelta] = {}
        self._info_suffixes: dict[str, str] = {}
        self._info_history: dict[str, list[tuple[pd.Timestamp, dict]]] = {}
        timeframes = definition.timeframes
        if timeframes is not None:
            for item in timeframes.informative:
                alias = item.alias
                self._info_engines[alias] = StreamingIndicatorEngine(
                    indicators=informative_indicators.get(alias, [])
                )
                self._info_offsets[alias] = interval_offset(item.interval)
                self._info_suffixes[alias] = f"_{item.interval}"
                self._info_history[alias] = []
        self._latest: CausalEnrichedBar | None = None

    # ── public API ──────────────────────────────────────────────────────

    @classmethod
    def from_strategy_definition(
        cls,
        definition: StrategyDefinition,
        primary_indicators: list[str],
        informative_indicators: dict[str, list[str]],
    ) -> CausalMultiTimeframeStreamingEnricher:
        """Create a Finbot-ready causal enricher from parsed strategy data.

        Args:
            definition: Parsed strategy definition.
            primary_indicators: Concrete indicator names for primary candles.
            informative_indicators: Concrete indicator names by alias.

        Returns:
            A stateful package-owned causal MTF streaming enricher.
        """
        return cls(
            definition=definition,
            primary_indicators=primary_indicators,
            informative_indicators=informative_indicators,
        )

    def update(self, alias: str, bar: dict) -> CausalEnrichedBar | None:
        """Ingest one closed candle by timeframe alias.

        Args:
            alias: ``"primary"`` for the decision timeframe, otherwise an
                informative timeframe alias.
            bar: Closed OHLCV bar dict with a parseable ``timestamp``.

        Returns:
            Latest enriched primary row for primary updates; None for
            informative-only updates.
        """
        if alias == "primary":
            return self.update_primary(bar)
        self.update_informative(alias, bar)
        return None

    def update_informative(self, alias: str, bar: dict) -> None:
        """Ingest one closed informative bar for the given alias."""
        engine = self._info_engines[alias]
        latest = engine.update(bar)
        row = _build_row(
            bar,
            _with_requested_columns(
                latest.values,
                self._info_indicators.get(alias, []),
            ),
        )
        self._info_history[alias].append((_bar_open_ts(bar), row))

    def update_primary(self, bar: dict) -> CausalEnrichedBar:
        """Ingest one closed primary bar; return the latest causal enriched bar."""
        latest = self._primary_engine.update(bar)
        merged = _build_row(
            bar,
            _with_requested_columns(latest.values, self._primary_indicators),
        )
        primary_open = _bar_open_ts(bar)
        for alias, offset in self._info_offsets.items():
            info_row = _latest_visible(self._info_history[alias], primary_open, offset)
            if info_row is not None:
                _merge_informative(merged, info_row, self._info_suffixes[alias])
        self._latest = CausalEnrichedBar(
            values=merged,
            timestamp=primary_open,
            is_ready=latest.is_ready,
        )
        return self._latest

    def latest(self) -> CausalEnrichedBar | None:
        """Return the most recent enriched bar without ingesting a bar."""
        return self._latest

    def reset(self) -> None:
        """Clear all per-timeframe state."""
        self._primary_engine.reset()
        for engine in self._info_engines.values():
            engine.reset()
        for alias in self._info_history:
            self._info_history[alias] = []
        self._latest = None

    @staticmethod
    def causal_enrich_bars(
        primary_bars: list[dict],
        informative_bars: dict[str, list[dict]],
        definition: StrategyDefinition,
        primary_indicators: list[str],
        informative_indicators: dict[str, list[str]],
        parallel: bool = True,
    ) -> "pd.DataFrame":
        """Produce a causal enriched DataFrame from raw bars.

        Package-level equivalent of ``build_causal_frame`` suitable for
        use in indicator job runners and other infrastructure code that
        must not import from the Finbar application layer.

        When ``parallel=True`` (default), informative timeframe enrichment
        runs in parallel threads with the primary enrichment, since each
        engine is completely independent until the per-bar merge step.

        Args:
            primary_bars: Primary OHLCV bar dicts sorted by timestamp.
            informative_bars: Informative bars keyed by timeframe alias.
            definition: Parsed strategy definition.
            primary_indicators: Primary indicator names.
            informative_indicators: Informative indicators by alias.
            parallel: Use thread-level parallelism for informative engines.

        Returns:
            DataFrame indexed by primary bar timestamp, with OHLCV,
            primary indicators, and suffixed informative columns.
        """
        # Pre-compute informative enrichment in parallel (engines are independent).
        info_enriched: dict[str, list[tuple[Any, dict]]] = {}
        if informative_bars and parallel:
            from concurrent.futures import ThreadPoolExecutor

            def _enrich_info(alias: str) -> list[tuple[Any, dict]]:
                engine = StreamingIndicatorEngine(
                    indicators=informative_indicators.get(alias, [])
                )
                suffix = _info_suffix_from_definition(definition, alias)
                results: list[tuple[Any, dict]] = []
                for b in informative_bars.get(alias, []):
                    latest = engine.update(b)
                    row = _build_row(
                        b,
                        _with_requested_columns(
                            latest.values,
                            informative_indicators.get(alias, []),
                        ),
                    )
                    results.append((_bar_open_ts(b), row))
                return results

            with ThreadPoolExecutor(
                max_workers=len(informative_bars)
            ) as executor:
                futures = {
                    alias: executor.submit(_enrich_info, alias)
                    for alias in informative_bars
                }
                for alias, future in futures.items():
                    info_enriched[alias] = future.result()
        else:
            # Sequential fallback: feed bars incrementally (original behaviour).
            enricher = CausalMultiTimeframeStreamingEnricher(
                definition=definition,
                primary_indicators=primary_indicators,
                informative_indicators=informative_indicators,
            )
            info_ptrs = {alias: 0 for alias in informative_bars}
            rows: list[dict] = []
            for bar in primary_bars:
                primary_open = _bar_open_ts(bar)
                for alias, ibars in informative_bars.items():
                    while info_ptrs[alias] < len(ibars):
                        candidate = ibars[info_ptrs[alias]]
                        if _bar_open_ts(candidate) <= primary_open:
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

        # Build primary enrichment (main thread) using pre-computed informative data.
        enricher = CausalMultiTimeframeStreamingEnricher(
            definition=definition,
            primary_indicators=primary_indicators,
            informative_indicators=informative_indicators,
        )
        # Seed informative history from pre-computed results.
        for alias, enriched in info_enriched.items():
            offset = enricher._info_offsets.get(alias)
            if offset is None:
                continue
            enricher._info_history[alias] = list(enriched)

        rows: list[dict] = []
        for bar in primary_bars:
            rows.append(enricher.update_primary(bar).values)

        if not rows:
            return pd.DataFrame()
        frame = pd.DataFrame(rows)
        ts = frame["timestamp"].tolist()
        index = parse_bar_timestamps(ts)
        return frame.drop(columns=["timestamp"]).set_index(index)


# ── module-level helpers ────────────────────────────────────────────────────


def _build_row(bar: dict, indicator_values: dict[str, Any]) -> dict[str, Any]:
    """Build a latest-row dict from a bar's OHLCV + computed indicator values."""
    row: dict[str, Any] = {k: v for k, v in bar.items()}
    for name, value in indicator_values.items():
        row[name] = value
    return row


def _with_requested_columns(values: dict[str, Any], names: list[str]) -> dict[str, Any]:
    """Return indicator values with requested-but-missing names as NaN."""
    complete = {name: float("nan") for name in names}
    complete.update(values)
    return complete


def _bar_open_ts(bar: dict) -> pd.Timestamp:
    """Parse a bar's timestamp to a UTC Timestamp (open time)."""
    ts = bar.get("timestamp")
    if ts is None:
        raise ValueError(
            "CausalMultiTimeframeStreamingEnricher requires bars with a"
            " parseable 'timestamp' field for no-lookahead MTF merge."
        )
    return parse_bar_timestamps([ts])[0]


def _info_suffix_from_definition(
    definition: StrategyDefinition,
    alias: str,
) -> str:
    """Return the column suffix for an informative timeframe alias."""
    timeframes = definition.timeframes
    if timeframes is not None:
        for item in timeframes.informative:
            if item.alias == alias:
                return f"_{item.interval}"
    return f"_{alias}"


def _latest_visible(
    history: list[tuple[pd.Timestamp, dict]],
    primary_open: pd.Timestamp,
    offset: pd.Timedelta,
) -> dict | None:
    """Return the latest informative row whose close is at or before primary open.

    An informative bar is visible only once it has fully closed: its close
    time (open + interval) must be <= the primary bar's open time. This
    replicates the batch merger's no-lookahead availability offset.
    """
    for open_ts, row in reversed(history):
        if open_ts + offset <= primary_open:
            return row
    return None


def _merge_informative(merged: dict, info_row: dict, suffix: str) -> None:
    """Merge non-OHLCV informative columns into the merged row, suffixed."""
    for col, value in info_row.items():
        if col in _OHLCV:
            continue
        merged[f"{col}{suffix}"] = value
