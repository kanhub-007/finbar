# Domain Model — Causal MTF Streaming Enrichment Parity

## Core Concepts

### Causal enriched bar
A primary-timeframe enriched bar whose fields are computed only from data that would have been available at the close of that primary bar.

```text
causal_enriched[t] = enrich(
    primary_bars where primary.close_time <= primary[t].close_time,
    informative_bars where informative.close_time <= primary[t].close_time,
)
```

No primary or informative bars after `t` may affect any value in `causal_enriched[t]`.

### Frame-dependent indicator
An indicator whose row value changes when the caller supplies more future rows to the batch frame. AMT/session VP currently falls into this category.

Example from current code:

- `compute_all_session_volume_profiles(df)` groups a whole calendar session.
- It computes one completed-session profile using every bar in that date.
- It broadcasts the completed profile to all rows in the session.
- Earlier rows therefore receive values influenced by later bars from the same session.

### Live-parity enrichment mode
A backtest/replay enrichment mode whose output for row `t` matches the live/WebSocket causal horizon. This mode is the required oracle for validating live-tradable strategies.

### Research/batch enrichment mode
The existing full-frame enrichment path. It may remain useful for exploration, but it must be explicitly marked as not live-parity safe for frame-dependent indicators such as session VP/AMT.

## Entities / Value Objects

| Name | Fields | Behaviour | Persisted? |
|---|---|---|---|
| `CausalEnrichedBar` | `timestamp`, OHLCV, indicator values, informative values | Immutable latest-row dict emitted by streaming MTF enrichment | No |
| `EnrichmentMode` | `BATCH_FULL_FRAME`, `LIVE_PARITY_STREAMING` | Declares the data horizon used by a backtest/enrichment run | No |
| `FrameDependencyReport` | `indicators`, `live_parity_safe`, `reason` | Explains whether a strategy uses indicators known to be frame-dependent | No |

## Interfaces

### New — `MultiTimeframeStreamingEnricher`
Package-level pure service. Lives in the strategy-runtime package.

```python
class MultiTimeframeStreamingEnricher(ABC):
    """Incrementally enrich primary bars with informative timeframe context.

    Callers feed closed informative and primary bars in chronological order.
    `update_primary()` returns the latest causal enriched primary bar.
    """

    def update_informative(self, alias: str, bar: dict) -> None: ...

    def update_primary(self, bar: dict) -> CausalEnrichedBar: ...

    def latest(self) -> CausalEnrichedBar | None: ...

    def reset(self) -> None: ...
```

### Existing — `MultiTimeframeBarEnricher`
Batch full-frame service. Current docstring says no-lookahead due to merge alignment. That must be clarified: merge alignment may be no-lookahead, but indicator handlers can still be frame-dependent before merge.

## Indicator Semantics Decision

For live-parity mode, `vp_poc`, `vp_vah`, and `vp_val` mean **expanding current-session volume profile**:

```text
vp_poc[t], vp_vah[t], vp_val[t]
  = compute_session_volume_profile(session bars from session open through t)
```

This is the causal definition that matches Finbot's WebSocket/prefix behavior today. Values are allowed to move during the session because live traders discover the session profile as bars close.

Rejected for live parity:

```text
Current completed-session broadcast:
  profile = compute_session_volume_profile(all bars in date)
  assign same profile to every row in date
```

because it leaks future session bars into earlier rows.

Alternatives kept for future explicit indicators:

| Alternative | Future indicator naming suggestion | Reason not chosen for this spec |
|---|---|---|
| Previous completed session profile | `prev_session_vp_poc`, `prev_session_vp_vah`, `prev_session_vp_val` | Useful, but does not match current Finbot live/prefix behavior |
| Rolling bar window | existing `rvp_*_N` family | Already explicit and causal; does not define plain `vp_*` |

## Performant Streaming Design

The implementation must not compute `enricher.enrich(primary[:i+1], info[:j+1])` for every bar except as a diagnostic/reference test. Prefix recomputation is correct but O(n²) and is not the production design.

### High-level object graph

```text
CausalMultiTimeframeStreamingEnricher
  ├── TimeframeStreamingState(primary)
  │     ├── StreamingIndicatorEngine          # O(1) scalar indicators: ATR, RSI, SMA, etc.
  │     ├── ExpandingSessionVolumeProfileState # O(session_bars × buckets), bounded by current session
  │     └── DerivedAmtWindowState              # O(k), k≈6, for shift-based AMT booleans
  ├── TimeframeStreamingState(h1)
  │     └── same components for informative timeframe indicators
  └── AsOfInformativeCache                     # latest closed informative enriched row per alias
```

### `TimeframeStreamingState`
One instance per timeframe alias. It owns all state required to turn one closed OHLCV bar into one enriched latest-row dict.

Responsibilities:
1. Preserve real timestamps.
2. Update scalar indicators through `StreamingIndicatorEngine`.
3. Update session VP through `ExpandingSessionVolumeProfileState`.
4. Derive auction/AMT booleans from the current row plus a tiny previous-row window.
5. Return one latest enriched row; do not mutate emitted prior rows.

### `ExpandingSessionVolumeProfileState`
A new state object for live-parity `vp_poc/vp_vah/vp_val`.

Contract:
```text
on new bar t:
  if date/session changed: reset current session buffer
  append bar t to current session buffer
  profile = compute_session_volume_profile(current_session_buffer)
  latest.vp_poc = profile.poc
  latest.vp_vah = profile.vah
  latest.vp_val = profile.val
```

Performance:
- Recomputes only the **current session**, never the full historical dataset.
- For 30m crypto bars this is at most ~48 bars/day × 100 buckets.
- For 1h informative bars this is at most ~24 bars/day × 100 buckets.
- Cost is bounded by session length, not total backtest length.

Why not incremental bucket updates in Slice 1?
- Current `compute_session_volume_profile()` uses dynamic buckets based on current session high/low. When a new high/low expands the range, historical volume must be rebucketed to match existing semantics exactly.
- Recomputing only the current session is simple, exact, and already performant for the target strategy.
- A later optimization can introduce fixed tick-size buckets for true O(buckets) updates if needed.

### `DerivedAmtWindowState`
AMT booleans are derived from current/past values (`shift(1)`, `shift(5)`, current IBS). They do not need full history. Keep a small deque of recently enriched rows and compute latest derived fields from that window.

Minimum required history:
- `acceptance_into_value`: previous row.
- `acceptance_outside_value`: previous row.
- `rejection_from_edge`: current row only plus IBS.
- `poc_rejection`: previous/shifted movement; keep enough rows for the current implementation.
- `balance_status`: uses `close.shift(5)`; keep at least 6 rows.

Implementation can either:
1. compute these formulas directly as scalar state, or
2. call the existing batch AMT handlers on a tiny real-timestamp DataFrame window.

Slice 1 should prefer option 2 for lower risk, then optimize to scalar state later if needed.

### MTF merge design
Informative bars are updated independently:

```python
stream.update_informative("h1", one_hour_bar)
```

The latest enriched informative row is cached per alias. On primary update:

```python
primary_latest = primary_state.update(primary_bar)
info_latest = latest informative row with close_time <= primary close_time
merged = suffix_and_merge(primary_latest, info_latest, suffix="_1h")
```

No historical primary frame is rebuilt. No informative future bar is visible to a primary row.

### Readiness / warmup
The streaming enricher emits latest rows from bar 1, but also reports readiness for required columns:

```text
ready = all required columns are present and non-NaN on latest row
```

Finbar backtest live-parity mode must still feed pre-ready bars to `JsonRuleBasedStrategy.on_bar()` for crossover state building, while suppressing orders until ready.

## Existing Code Findings

### `domain/services/volume_profile.py`
`compute_all_session_volume_profiles()` currently:

```python
for date, idx in date_series.groupby(date_series).groups.items():
    session = df.loc[idx]
    profile = compute_session_volume_profile(session)
    poc_map[date] = profile.poc
    ...
result["vp_poc"] = date_series.map(poc_map)
```

This is completed-session broadcast. For row `t` early in a session, `session = df.loc[idx]` includes rows after `t` when the caller supplies the full frame.

### `indicators/handlers/market_profile_amt.py`
`near_vah`, `near_val`, `rejection_from_edge`, `value_area_width_pct`, and related AMT fields are derived from `vp_poc/vp_vah/vp_val`. Their internal formulas use current/past rows, but they inherit lookahead if their VP inputs are completed-session values.

### `indicators/streaming/windowed_indicator_state.py`
The windowed fallback builds a DataFrame with:

```python
pd.date_range("2024-01-01", periods=n, freq="h")
```

This discards real candle timestamps. Any session/date-sensitive indicator computed through this fallback cannot be trusted for live parity until timestamp preservation is fixed.

### `indicators/multi_timeframe_bar_enricher.py`
The merge step is as-of/no-lookahead, but each timeframe's indicators are computed before merge using the batch calculator. Therefore frame-dependent indicators can leak future data before the no-lookahead merge step.

## Entity vs ORM separation
N/A. This is a pure runtime computation capability.
