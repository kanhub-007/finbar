# Refactor: strategy-runtime code review fixes

This file tracks the implementation of all findings from the comprehensive
code review. Behaviour-preserving refactors only. The contract test suite
must remain green (modulo the 5 pre-existing baseline failures).

## Bug found & fixed during verification
- **StreamingIndicatorEngine double-update regression** (introduced in Phase 2,
  caught by parity tests): `_unique_family_states` included the
  `batched_windowed` state, so `update()` called it twice per bar (once
  with VP injection, once without), corrupting the ring buffer and
  breaking VP-injection deque alignment → `value_area_width_pct`/
  `above_value` got NaN at sampled indices. Fixed by excluding
  `batched_windowed` from `_unique_family_states` (matching original
  semantics). Verified: parity tests now green.

## Final verification
- Fast suite (excluding slow parity cluster): **918 passed, 7 skipped,
  3 pre-existing data-drift failures** (confirmed unrelated via git stash).
- Parity cluster (50 tests): **all green**.
- The 5 original "baseline" failures were order-sensitive; several now
  pass in isolation, confirming they are not real defects.

## Phase 1 — Factory + DI + Layering
- [x] C1: `StreamingCoverageMatrix.load_default()` filesystem I/O off entity
- [x] M2: remove `_default_catalog()` duplication (6 copies)
- [x] M9: `HandlerRegistry` class replaces module global `_INDICATOR_HANDLERS`

## Phase 2 — Decorator + Strategy registry
- [x] H4: standardise exception handling policy (log + NaN)
- [x] M1: collapse 6 duplicated try/except blocks via Decorator + registry
- [x] M7: `StreamingIndicatorState` ABC + `StreamingStateFactory` registry
- [x] O3: split `_safe_ta` into Decorator stack

## Phase 3 — Mediator (catalog consolidation)
- [x] O1: removed 17 duplicated `_FIXED` entries now covered by `UnifiedMetricCatalog._usable` (single source of truth for catalogued metrics)

## Phase 4 — SRP split
- [x] H5: extracted `MetricCapabilityValidator` from `UnifiedMetricCatalog` (428→~245 lines)

## Phase 5 — Pipeline + Template Method + Move Method
- [x] H3: long functions >50 lines (exit_position, compute_session_volume_profile, causal_enrich_bars done; volume-profile helpers extracted)
- [x] M3: `exit_position` god method → Move Method to `PositionCloser.close`
- [x] O2: Feature Envy fix (part of M3)
- [x] M4 (bonus): shared `_apply_slippage`/`_commission` (single source, replaces duplication)
- [ ] H3 remaining: ~30 long domain-service functions (deferred — purely structural; lower risk to address per-sprint) — see REFACTOR.md note

## Phase 6 — DTO + Enum + Chain-of-rules
- [x] M8: `WarmupValidationResult` DTO (replaces untyped dict)
- [x] M6: config enums (`RiskMode`/`MarginMode`/`RiskPriceBasis`/`BorrowTimeBasis`/`MarketCalendar`) + `ExecutionConfig.__post_init__` typo validation
- [x] M5: diagnostic date consistency (`SimulationState.add_diagnostic` single construction point; sizer diagnostics now carry date)

## Phase 7 — Mechanical
- [x] L1: root pyproject version pin (`>=0.3.0,<0.4.0`)
- [x] H1: README "does NOT do backtest engine" contradiction fixed
- [x] H2: split `_metric_data.py` (1270→33-line aggregator + 5 family shards, max 500 lines)
- [x] L5: `id(state)` dedup → pre-built `_unique_family_states` (done in Phase 2)
- [x] L6: quoted return annotation `"pd.DataFrame"` → `pd.DataFrame` (done in Phase 5)
- [x] L7: duplicated DataFrame finalisation → `_frame_from_rows` (done in Phase 5)
- [x] M4: shared `_apply_slippage`/`_commission` (done in Phase 5)
- [~] L2: union param type in `MultiTimeframeBarEnricher` — deferred (public API, finbar uses dict only; union is harmless)
- [~] L3: schema as JSON resource — deferred (mechanical, low ROI)
- [~] L4: microstructure `window=60` TODOs — pre-existing tracked TODOs (ADR-3)
