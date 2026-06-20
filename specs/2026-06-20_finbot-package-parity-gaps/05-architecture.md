# Architecture Decisions — Finbot ⇄ Strategy Runtime Package Parity Gaps

This file records the decisions that shape the spec, including the **amendment**
to the original extract-package spec's ADR-2. Numbering continues from the
original `2026-06-14_extract-strategy-runtime-package/05-architecture.md`
(ADR-1 through ADR-5).

---

# ADR-6: The package owns the fill/sizing primitives (amends ADR-2)

**Context:**
The original extract-package spec codified ADR-2: *"Runtime package stops at
signal generation. It has no order model, exchange gateway, database, job
manager, or network fetcher. Finbar remains responsible for backtest execution
assumptions, fills, slippage, fees."*

That boundary was correct **as a prohibition on venue/exchange plumbing**, but
it was phrased broadly enough to also forbid the *deterministic* fill/sizing
math. In practice, that math (sizing, entry timing, stop/target fills,
liquidation, commission, PnL) is now duplicated across finbar-the-app
(`PositionExecutor` + `PositionSizer` + collaborators) and finbot
(`OrderPlanner` + `DryRunSubmissionStrategy`) — and the two copies **disagree**.
This duplication is precisely where backtest↔replay divergence silently creeps
in, which is the one thing the package exists to prevent.

A three-layer analysis clarifies what is actually shared vs genuinely different:

| Layer | Responsibility | Shared? |
|---|---|---|
| A. Bar → enriched bar | MTF merge + per-TF indicators + features + warmup-readiness | Yes (Gap #1) |
| B. Signal → fill → PnL | sizing, entry timing, stop/target, liquidation, commission | **Yes (Gap #2)** — deterministic primitives |
| C. Actual order to venue | REST/websocket to Hyperliquid, cloid, partial fills | No — stays in finbot |

Layer B is pure: given a signal, a bar, and a position, compute the size/fill/
PnL — no venue, no async, no network. Layer C is what ADR-2 was really
forbidding (live exchange plumbing), and Layer C stays out of the package
regardless.

**Decision:**
The package owns **Layer A** (`MultiTimeframeBarEnricher`,
`RequiredDataValidator`) and **Layer B** (**primitives**: `PositionSizer`,
`PositionOpener`, `PositionCloser`, `IntrabarExitResolver`,
`MarginAccountManager`, `PositionExecutor`, `ExecutionConfig`,
`LeverageConfig`, `TradeRecord`, `PendingEntry`/`PendingExit`,
`SimulationState`, plus the pure metric services), under
`finbar_strategy_runtime.indicators` and `finbar_strategy_runtime.simulation`
respectively. Layer C (venue) remains in finbot.

ADR-2 is **amended, not violated**: its intent — "no exchange/order plumbing in
the package" — is preserved (Layer C is still banned). What changes is that the
*deterministic* fill/sizing math (Layer B) is recognized as legitimate shared
domain logic, on the same footing as indicator math. The restated boundary:

> The package owns the shared primitive functions for producing an enriched
> bar, a sized order, and a deterministic fill/PnL. It never owns a loop/driver
> and never touches a real exchange.

**Consequences:**
- Backtest and finbot replay/dry-run size/fill/PnL through the **same**
  primitives → backtest↔replay parity is by construction, not by careful
  re-implementation.
- The package gains a `pandas`/`numpy`-only `simulation` subpackage of pure
  services; no new third-party or app dependencies.
- Finbar's `BacktestRunner` keeps its loop; only its imports change. Finbot's
  dry-run composes the shared primitives; finbot live keeps its own venue path.

---

# ADR-7: Parity is exact for replay, best-effort for live

**Context:**
The motivating constraint says behaviour must be "identical between Finbar and
Finbot." That conflates two paths with different guarantees:

- **Replay / dry-run** — finbot's real loop drives the shared primitives, with a
  fake exchange that fills using the *same* Layer-B math as the backtest.
  Deterministic → **can** be bit-for-bit identical.
- **True live on Hyperliquid** — the real loop drives the shared decision/sizing
  primitives, but **fills come from the exchange** (latency, partial fills,
  funding skew). By construction **cannot** be bit-identical to any backtest.

**Decision:**
State the parity guarantee precisely: the shared primitives guarantee
**backtest↔replay parity** (exact). **backtest↔live parity** is best-effort by
nature and is *not* what the primitives guarantee. Finbot's live
`OrderPlanner` / `LiveSubmissionStrategy` / submission boundary (Layer C)
legitimately remain separate; there is no shadow bookkeeping (live uses the
exchange as the single source of truth for fills).

**Consequences:**
- The acceptance test mocks only the websocket + exchange boundary and asserts
  on the replay path — exactly where exact parity is achievable.
- The fill primitives are not mis-sold as a live-execution guarantee.
- Slice 2 is scoped to "replay + dry-run use the shared fill primitives"; the
  live submission layer is explicitly out of scope.

---

# ADR-8: Slice 1 uses the batch-on-warmup-window enricher (pandas path)

**Context:**
Finbot is streaming (one primary candle at a time), while backtest is batch.
The enricher could be (a) batch-over-warmup-window each candle, or (b) a
streaming incremental enricher. Option (b) requires the existing
`StreamingIndicatorEngine`, which is single-timeframe-only and does **not**
support AMT / volume-profile / market-profile indicators — exactly the
indicators the production target strategy uses. So (b) would not run the target
strategy today.

**Decision:**
Slice 1 implements `MultiTimeframeBarEnricher` as a **batch** service called
over the trimmed warmup window (finbot already caches up to 500 bars and its
own docstring documents and accepts the `O(window)` per-candle cost). It uses
the pandas path, which supports every strategy including the target.

A streaming MTF enricher is deferred and should be tackled together with
extending the streaming engine to AMT/VP — tracked as a separate spec.

**Consequences:**
- Slice 1 works for *every* strategy, including the production target.
- No-lookahead is preserved: informative closed bars are fed via finbot's cache;
  `merge_timeframes`'s as-of + interval_offset alignment already guarantees
  correct streaming semantics.
- `O(window)` per candle is the known, accepted cost; the `max_length` knob
  bounds memory. Optimization is a later concern.

---

# ADR-9: Versioning — Slice 1 → 0.2.0, Slice 2 → 0.3.0

**Context:**
Finbot pins `finbar-strategy-runtime[pandas,yaml]>=0.1.0,<0.2.0`. The `<0.2.0`
cap blocks any minor bump. Each slice adds public API surface (new services),
which semver says is a *minor* bump.

**Decision:**
- Slice 1 ships the enricher + validator as package **0.2.0**. Finbot bumps its
  pin to `>=0.2.0,<0.3.0`.
- Slice 2 ships the fill/sizing primitives as package **0.3.0**. Finbot bumps
  its pin to `>=0.3.0,<0.4.0`.

`0.1.x` patches are reserved for bug fixes only; new public surfaces get a minor
bump even during active development, because misusing the patch number as a
release-coordination trick makes the version untrustworthy.

**Consequences:**
- Each slice is a discrete, independently consumable release. Finbot can adopt
  Slice 1 (unblock MTF signals) without waiting for Slice 2.
- Finbot's pin bump is a 1-line `pyproject.toml` change per slice; coordinated
  but trivial.
- The package `__version__` (in `__init__.py`) and the `pyproject.toml`
  `version` must always agree.

---

# ADR-10: Ship sliced — Layer A first, Layer B next (no Slice 3)

**Context:**
Slice 1 (the enricher + validator) is low-risk: pure services + thin finbot
wiring + golden-frame regression. Slice 2 (the fill primitives) is higher-risk:
it moves ~10 services + metrics + 7 entities and rewires finbar's loop imports.
Bundling them couples a safe, high-value unblock (all MTF strategies start
firing in finbot) to a riskier refactor.

Earlier drafts proposed a Slice 3 `replay()` facade. That is **dropped**: replay
must exercise finbot's real loop with fake data, so a shared one-shot facade
would defeat the test's purpose.

**Decision:**
Ship Slice 1 first, Slice 2 next. **No Slice 3.** Capture golden references
*before* each refactor so both slices are provably behaviour-preserving.

**Consequences:**
- The production MTF strategy is unblocked in finbot as soon as Slice 1 lands.
- Slice 2 benefits from the integration experience and finbot wiring pattern
  established in Slice 1.
- Blast radius of any regression is bounded to one slice.

---

# ADR-11: No shared loop/driver — parity via shared primitives + a documented timing contract

**Context:**
It is tempting to extract finbar's `_run_loop` into a shared "steppable
simulator" so backtest and replay provably run the same per-bar ordering.
But replay's entire purpose is to test **finbot's real live loop** (`process_
closed_candle`) with fake data. If both paths called a shared `step()` from the
package, the test would no longer exercise finbot's actual loop — it would
test the shared stepper instead, hiding finbot-side ordering bugs.

The two loops are also genuinely different in shape: finbar iterates a complete
DataFrame; finbot reacts to websocket closes and submits to an exchange. A
shared loop would force one shape onto both.

**Decision:**
The package delivers **primitives only** — no `run()`, no `step()`, no
`SimulationResult`, no `replay()` facade. Finbar's `BacktestRunner` keeps its
loop; finbot's `process_closed_candle` keeps its loop. Both loops call the same
primitives (`MultiTimeframeBarEnricher`, `RequiredDataValidator`,
`PositionSizer`, `PositionExecutor`, `IntrabarExitResolver`, `PositionCloser`,
`ExecutionConfig`, …).

The per-bar **timing ordering** (entries fill at next-bar open; exits are
intrabar gap-aware; warmup bars feed `on_bar` for state but aren't traded) is a
**documented parity contract** that both loops must honour. It is **not**
enforced by shared code; it is enforced by the replay acceptance test, which
fails if either loop diverges.

**Consequences:**
- Replay genuinely tests finbot's loop, not a shared stepper.
- The fill **math** is guaranteed identical (shared primitives); the fill
  **timing** is each loop's responsibility, verified end-to-end.
- Adding a future shared stepper remains possible if divergence proves
  unmanageable, but it is deliberately not the starting point.

---

# Relationship to the original extract-package spec (ADR-1..5)

| Original ADR | This spec |
|---|---|
| ADR-1: Extract runtime into a package | Continued — this spec *extends* the package with two more layers of primitives. |
| ADR-2: Package stops at signal generation | **Amended by ADR-6** above. The prohibition on venue/exchange plumbing (Layer C) stands; the deterministic fill/sizing primitives (Layer B) are admitted as shared domain logic. |
| ADR-3: Schema version ≠ package version | Unchanged. Strategy `schema_version` stays `2.0`; package semver moves to `0.2.0` / `0.3.0`. |
| ADR-4: Finbar adapters remain in Finbar | Continued — finbar's `BacktestRunner` loop + result builder stay; only imports change. Finbot keeps its own venue adapters (Layer C). |
| ADR-5: (compatibility/parity tests) | Continued — the golden-frame and golden-result tests in this spec are direct successors of the original parity-contract tests. |
