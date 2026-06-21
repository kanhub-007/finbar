# Implementation Guide — Causal MTF Streaming Enrichment Parity

## Step 1: Lock the failing behavior with contract tests
**Files:**
- `packages/strategy-runtime/tests/contract/test_causal_mtf_streaming_enrichment.py` (new)
- `packages/strategy-runtime/tests/contract/fixtures/` or existing deterministic fixture helpers

Add tests from `02-scenarios.md` Scenario 1 and Scenario 2.

Commit the same SOL fixtures used by the Finbot investigation under the package contract fixtures, for example:

```text
packages/strategy-runtime/tests/fixtures/parity/sol_30min.csv
packages/strategy-runtime/tests/fixtures/parity/sol_1h.csv
```

The fixture timestamps must be int seconds, matching Finbot/Hyperliquid production bars.

**Purpose:** prove the existing full-frame batch enrichment is not a valid live-parity oracle for AMT/session VP.

**Verify:**
```bash
cd C:\HAL\Github\finbar
pytest packages/strategy-runtime/tests/contract/test_causal_mtf_streaming_enrichment.py -q
```

**Expected red:** full-frame first signal row is 95 while streaming-prefix first signal row is 17.

---

## Step 2: Clarify / fix session VP semantics
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/domain/services/volume_profile.py`
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/volume_profile.py`

Current function of concern:

```python
compute_all_session_volume_profiles(df)
```

Current behavior computes a completed profile for the whole session and broadcasts it to all session rows. That is not live causal.

Implement the chosen live-parity definition:

```python
compute_expanding_session_volume_profiles(df)
```

Each row uses session bars from session open through that row. Do **not** change `compute_all_session_volume_profiles()` silently; keep it as completed-session batch/research behavior for reproducibility.

Add a live-parity path in the handler layer, e.g. an explicit calculator/enrichment mode that calls the expanding function for `vp_poc/vp_vah/vp_val` when `enrichment_mode="live_parity_streaming"`.

**Common mistake:** changing `compute_all_session_volume_profiles()` globally will alter historical backtest results and hide the distinction between research batch mode and live-parity mode.

---

## Step 3: Preserve timestamps in windowed streaming fallback
**File:**
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/windowed_indicator_state.py`

Current issue:

```python
self._index = pd.date_range("2024-01-01", periods=n, freq="h")
```

This loses actual session boundaries. Update `_to_dataframe()` to derive the index from each bar's `timestamp` when present:

- numeric int/float timestamps: treat as Unix **seconds** by default (Finbot/Hyperliquid production format)
- ISO strings / Python datetimes: parse with `pd.to_datetime(..., utc=True)`
- missing timestamps: fail clearly for session/date-sensitive indicators (`vp_*`, AMT/profile/VWAP families) instead of fabricating dates

Keep a deterministic fallback only for indicators that do not use date/session semantics.

**Verify:**
- Windowed fallback over bars spanning a date boundary must preserve that boundary in `df.index.date`.
- VP/AMT tests must fail before this fix and pass after.
- A missing timestamp for `vp_poc` raises a clear `ValueError` (or equivalent explicit failure), not a silent fake-session result.

---

## Step 4: Add performant package-level MTF streaming enricher
**Files:**
- `packages/strategy-runtime/finbar_strategy_runtime/domain/interfaces/multi_timeframe_streaming_enricher.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/multi_timeframe_streaming_enricher.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/timeframe_streaming_state.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/expanding_session_volume_profile_state.py` (new)
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/derived_amt_window_state.py` (new)

Responsibilities:

1. Maintain per-timeframe state; do not rebuild the full historical frame per bar.
2. Accept informative bars through `update_informative(alias, bar)`.
3. Accept primary bars through `update_primary(bar)`.
4. Compute only the latest causal primary enriched row.
5. Merge informative values using the latest informative bar closed at or before the primary bar close.
6. Return a latest-row dict / `CausalEnrichedBar` suitable for `JsonRuleBasedStrategy.on_bar()`.
7. Use expanding current-session VP for live-parity `vp_*` values.

Production design:

```text
update_primary(bar)
  -> primary_state.update(bar)
       -> StreamingIndicatorEngine.update(bar)                 # scalar O(1)
       -> ExpandingSessionVolumeProfileState.update(bar)       # current-session only
       -> DerivedAmtWindowState.update(latest_row)             # tiny window
  -> merge latest informative rows by as-of close time
  -> return latest merged enriched row
```

Do **not** implement production live-parity by repeatedly calling:

```python
enricher.enrich(primary[:i+1], informative_prefix)
```

That prefix-recompute loop is allowed only as a red/green reference oracle in tests. It is O(n²) and is the performance problem this design avoids.

Design notes:
- Use constructor injection for calculators / converters / merger helpers.
- Do not import Finbot or app-layer backtest code.
- Keep the existing `MultiTimeframeBarEnricher` only as the explicitly labelled batch/research service.

---

## Step 5: Add Finbar backtest live-parity mode
**Files:**
- `finbar/core/application/use_cases/backtest_strategy_definition.py`
- relevant DTO/request files for adding `enrichment_mode`
- startup factory wiring

Add a request-level option:

```python
enrichment_mode: Literal["batch_full_frame", "live_parity_streaming"]
```

Default can remain existing batch behavior initially, but production/live-validation workflows should opt into `live_parity_streaming`.

In live-parity mode, the backtest driver must get each bar's latest causal enriched row from the streaming enricher, not from a precomputed full frame.

---

## Step 6: Update result metadata / warnings
**Files:**
- Backtest result DTO / mapper
- UI/API presenter if relevant

When `batch_full_frame` is used with frame-dependent indicators (`vp_poc`, `vp_vah`, `vp_val`, AMT fields depending on them), mark:

```json
{
  "enrichment_mode": "batch_full_frame",
  "live_parity_safe": false,
  "warnings": ["Session VP/AMT indicators are frame-dependent in batch_full_frame mode"]
}
```

---

## Step 7: Finbot follow-up (out of scope here)
Once package exposes `MultiTimeframeStreamingEnricher`, Finbot should replace its adapter's per-candle full-window recomputation with the shared streaming enricher. That follow-up belongs in the Finbot repo.
