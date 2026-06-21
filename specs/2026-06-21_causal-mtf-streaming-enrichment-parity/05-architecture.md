# Architecture Decisions — Causal MTF Streaming Enrichment Parity

## ADR-1: Live-parity backtests must use causal enrichment, not full-frame batch enrichment

**Context:**
Finbot receives closed bars one at a time. At primary bar `t`, it cannot know future primary bars or future informative bars. Current Finbar batch enrichment computes indicators over the full historical frame before the backtest loop. For AMT/session VP indicators, this changes values at earlier rows because completed-session volume profiles are broadcast to every row in the session.

**Decision:**
Introduce an explicit `live_parity_streaming` enrichment mode. In this mode, every enriched primary row must be computed from the causal data horizon available at that bar close. This mode replaces full-frame batch enrichment as the authoritative oracle for validating live-tradable behavior and Finbot parity.

**Consequences:**
- Existing batch backtests may produce different trades for VP/AMT strategies.
- This difference is expected and should be surfaced to users through metadata/warnings.
- Backtests intended for live deployment must use `live_parity_streaming`.

---

## ADR-2: Keep full-frame batch enrichment as a separate research mode

**Context:**
Full-frame batch enrichment may still be useful for exploratory analytics, completed-session studies, or non-live research. Removing it immediately would be disruptive.

**Decision:**
Do not delete `MultiTimeframeBarEnricher` or `compute_all_session_volume_profiles()`. Instead, label the mode explicitly as `batch_full_frame` and mark it not live-parity safe when frame-dependent indicators are present.

**Consequences:**
- Existing results can still be reproduced.
- Users must choose the correct mode for their purpose.
- The UI/API should make live-parity status visible.

---

## ADR-3: Package owns causal MTF streaming enrichment

**Context:**
Finbar owns strategy parsing, indicator semantics, MTF merge semantics, and publishes `finbar_strategy_runtime` to Finbot. If Finbot implements its own streaming/enrichment semantics, parity will drift again.

**Decision:**
The causal MTF streaming enricher belongs in `finbar_strategy_runtime`. Both Finbar live-parity backtests and Finbot live/replay must consume the same package service.

**Consequences:**
- Finbot remains a consumer; it should not implement AMT/VP or MTF merge semantics.
- The package API must be stable enough for Finbot.
- Tests should live in both repos: package contract tests for enrichment semantics, Finbot integration tests for live-loop wiring.

---

## ADR-4: Live-parity `vp_*` means expanding current-session profile

**Context:**
The name `vp_poc/vp_vah/vp_val` currently means “completed current session profile broadcast to every row in the session” in batch mode. That definition is not live-causal for intraday decisions.

**Decision:**
In `live_parity_streaming` mode, `vp_poc/vp_vah/vp_val` mean expanding current-session profile: each bar uses session bars from session open through the current bar. This matches Finbot WebSocket/prefix behavior and avoids future leakage.

**Consequences:**
- The production strategy may change signals compared with historical full-frame batch results.
- Historical optimized results based on completed-session broadcast have lookahead bias for intraday/live use.
- Strategy authors get a clear semantic contract instead of implicit frame-dependent behavior.

---

## ADR-5: Streaming implementation must be stateful and bounded, not prefix recompute

**Context:**
A prefix-reference loop (`enrich(primary[:i+1])` for every bar) is correct but O(n²). It is useful as a test oracle but not acceptable for production backtests or Finbot live use.

**Decision:**
Implement a stateful `CausalMultiTimeframeStreamingEnricher` composed of per-timeframe state objects. Scalar indicators use existing `StreamingIndicatorEngine`; live-parity VP uses `ExpandingSessionVolumeProfileState` over only the current session; AMT derived fields use a tiny recent-row window; MTF merge uses cached latest informative rows.

**Consequences:**
- Per-bar cost is bounded by current session length / small indicator windows, not total historical bars.
- The implementation remains exact for the chosen expanding-session VP semantics.
- Future optimization can replace current-session VP recompute with fixed tick-size bucket state if needed.
