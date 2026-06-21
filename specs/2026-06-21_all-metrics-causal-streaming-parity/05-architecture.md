# Architecture Decisions — All-Metrics Causal Streaming Parity

## ADR-1: Causal prefix oracle is the source of truth, not full-frame batch rows

**Context:**
Legacy batch enrichment often computes an entire frame at once. For some session/profile metrics, historical rows can be affected by later rows in the same frame/session. That is useful for research but impossible in live trading.

**Decision:**
For `live_parity_streaming`, correctness is defined as: streaming value at row `t` equals the batch calculator run on `bars[:t+1]`, taking the last row. Full-frame batch row `t` is not a valid live-parity oracle.

**Consequences:**
- Tests catch future leakage directly.
- Some causal values intentionally differ from old batch values for earlier rows.
- `batch_full_frame` remains available as research mode but must be labelled not live-parity safe when frame-dependent metrics are used.

## ADR-2: The package owns all enrichment semantics

**Context:**
Finbar and Finbot can only stay in parity if they call the same enrichment implementation. If either app keeps local indicator orchestration, metrics will drift.

**Decision:**
`finbar_strategy_runtime` owns:
- per-metric streaming state
- causal MTF merge semantics
- feature calculation needed before strategy evaluation
- coverage classifier / matrix
- readiness/warmup semantics for enriched rows

Finbar and Finbot own loops, I/O, persistence, and exchange integration.

**Consequences:**
- Finbot can consume package updates without reimplementing indicators.
- Finbar backtests and Finbot live/replay evaluate the same enriched scalar rows.
- The package must remain pure: no imports from `finbar`, `finbot`, DB/ORM, exchange SDKs, or app frameworks.

## ADR-3: Safety gate during rollout; empty unsupported set at completion

**Context:**
The current streaming path has 22 silent wrong metrics and 23 loud NaN/raise metrics. Letting those drive default backtests is unsafe.

**Decision:**
Add a package-owned coverage classifier immediately. During rollout, any unsupported metric prevents silent causal use: Finbar either falls back to `batch_full_frame` with warnings and `live_parity_safe=False`, or fails explicitly. After Slice 2, every catalog metric must be classified `STREAMING_CORRECT` and the unsupported set is empty.

**Consequences:**
- The default is safe before all metric families are fixed.
- Users get named diagnostics for metrics blocking live-parity.
- The safety gate remains as defense-in-depth for future metrics.

## ADR-4: Correctness before O(1), but bounded/streaming design remains the target

**Context:**
Some metrics have straightforward O(1) states; others require session windows, rolling profiles, or dependency-aware recompute. Requiring O(1) for every metric before enabling causal correctness would delay parity unnecessarily.

**Decision:**
Every metric must be causally correct first. Implementation may be:
- O(1) dedicated state,
- bounded rolling/session state,
- dependency-aware windowed recompute,
- or a correctness-first prefix-safe fallback for rare/heavy metrics.

Where performance matters (`rvp_*`, session VP, common indicators), use dedicated bounded states. Track performance budgets separately.

**Consequences:**
- No metric silently returns a wrong value because an optimized state does not exist yet.
- The implementation can improve performance family by family without changing public semantics.
- Extremely heavy metrics may be correct but slower until optimized.

## ADR-5: Coverage matrix is empirical and package-owned

**Context:**
A hand-written supported/unsupported list can drift. A new metric or handler change must update coverage evidence.

**Decision:**
Generate `streaming_coverage_matrix.json` from deterministic causal-prefix sweeps. Commit the matrix as a package resource. The classifier reads it; tests assert its keys match the unified catalog.

**Consequences:**
- Reviewers see metric coverage changes in diffs.
- Finbot can query coverage without running an expensive sweep.
- Adding a metric requires adding coverage evidence.

## ADR-6: Saved-strategy artifacts must record enrichment horizon

**Context:**
Saved-strategy backtests consume pre-enriched artifacts from the indicator-job pipeline. A causal backtest must not silently consume an old batch artifact.

**Decision:**
Any persisted enriched-bars artifact records `enrichment_mode` and enough strategy/indicator hash data to know whether it is compatible with the requested backtest. A causal request requires a causal artifact or regenerates one.

**Consequences:**
- Saved and inline strategies can produce identical causal backtests.
- Cached artifacts remain safe.
- Batch artifacts remain useful for research but are labelled.

## ADR-7: Finbot consumes the package API; live fills stay exchange-owned

**Context:**
This spec is about enrichment, not execution. Finbot live trading receives real exchange fills; those cannot and should not be simulated by the package.

**Decision:**
Finbot uses package causal enrichment and rule evaluation for decisions. Finbot replay may assert enriched-row and signal parity with Finbar. Live PnL remains best-effort because real fills, latency, partial fills, and exchange state are external.

**Consequences:**
- Backtest-vs-Finbot replay can be exact for enriched rows and signal timestamps.
- Live decisions use the same data horizon and strategy semantics as backtest.
- No Hyperliquid code enters the package.

## ADR-8: One-class-per-file applies to new metric states

**Context:**
The streaming engine will gain many state classes. Bundling them into one large file would violate the project's one-class-per-file and size rules.

**Decision:**
Each new state, entity, interface, classifier, and DTO lives in its own file. Shared helper functions may live alongside the single class they support or in small utility modules.

**Consequences:**
- Metric families remain reviewable.
- Future optimizations can replace one state without affecting unrelated families.
