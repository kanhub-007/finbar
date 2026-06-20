# Finbot ⇄ Strategy Runtime Package — Parity Gaps

> **Status:** Spec rewrite. Supersedes the original single-file problem
> statement, which is absorbed into the Context below.
>
> **Owner of this spec:** the **finbar** repo, because finbar owns and publishes
> the `finbar_strategy_runtime` package. Finbot (`C:\HAL\Github\finbot`) is the
> consumer; the parity test that validates this work lives in finbot.
>
> **Correction vs. earlier drafts:** Finbot's use case is **live trading** on
> an incoming websocket stream — not "replay". "Replay" is the *integration
> test* (fake data through the real live pipeline). There is **no shared batch
> simulator**: parity comes from both apps calling the **same primitive
> library functions**, while each keeps its own loop/driver and finbot uses the
> real exchange (no shadow bookkeeping). See the flowcharts in §Context.

---

## User Story

As a trader, I want the **production strategy** `14_amt_value_reject_30m_1h_mtf.yaml`
(10% risk / 10x leverage) to run through Finbot's live/replay pipeline and
produce the **same trades and PnL** as the Finbar backtest, so that a backtest
result is a trustworthy prediction of live behaviour — not a number that
diverges the moment the strategy goes live.

## Context

### The two projects and the hard constraint

- **Finbar** (this repo) authors, validates, backtests, and optimizes trading
  strategies. It also owns and publishes the **`finbar_strategy_runtime`**
  package (`packages/strategy-runtime/`), shared with Finbot.
- **Finbot** (`C:\HAL\Github\finbot`) is the **live trading runtime** for
  Finbar-authored strategies. It connects to Hyperliquid, consumes realtime
  market/account data, evaluates strategies, places/monitors/cancels orders,
  reconciles state, and enforces live risk controls.

The two **use cases** (each app keeps its own loop/driver):

- **Finbar = backtest.** Has all bars at once, loops over them bar-by-bar.
- **Finbot = live trading.** Receives OHLCV per websocket close (a 30min close,
  a 1h close), evaluates each, and submits real orders to Hyperliquid.

"Replay" is **not** a use case — it is the *integration test*: feed finbot's
real live pipeline mocked historical websocket data (a fake exchange gateway)
and assert the output equals the Finbar backtest.

The hard constraint (non-negotiable):

> **The strategy-decision behavior that both loops invoke must be identical
> and *reused* — parsed, enriched, evaluated, and sized by the same package
> functions — never re-implemented in either app.**

The loops themselves and the venue are genuinely different and stay in each
app. Parity is achieved by making both loops call the **same primitive
library functions** (enrichment + sizing + fill math), not by a shared batch
runner. Finbot must not re-implement parsing, indicator math, condition
evaluation, risk/stop calculation, bar merging, or the fill/sizing math.

### The three-layer model (the design lens for this spec)

"Bar in → trade out" is a similar flow in both apps, but it splits into three
layers with different sharing rules. This spec is built on that split:

| Layer | Responsibility | Shared in package? | Notes |
|---|---|---|---|
| **A. Bar → enriched bar** | MTF merge + per-timeframe indicators + features | **Yes — Gap #1** | Pure: bars in → frame out. No venue. Today *partly* shared (primitives) but the **orchestration** is missing from the package. |
| **B. Signal → fill → PnL** | sizing, entry timing, stop/target, liquidation, commission, equity | **Yes — Gap #2** | Pure deterministic model. No venue, no async, no network. Today **duplicated and divergent** (backtest vs finbot dry-run disagree). |
| **C. Actual order to venue** | REST/websocket calls to Hyperliquid, cloid, partial fills, order state | **No — stays in finbot** | Genuinely different from backtest by construction. ADR-2 forbids it in the package. |

The package's job becomes: **the shared primitive functions for Layers A + B**
(enrichment, warmup-readiness, sizing, fill math). It never owns a loop/driver
and never touches a real exchange (Layer C). This *amends* (does not violate)
ADR-2 — see `05-architecture.md` ADR-6.

### The two flows, side by side (canonical overview)

Legend for every step below:

```
[SHARED]  already in finbar_strategy_runtime — BOTH use it (leave alone)
[GAP-1]   Layer A gap — must ADD to package (Slice 1): enrichment + warmup
[GAP-2]   Layer B gap — must ADD to package (Slice 2): sizing + fill model
[APP]     stays in THIS app, never shared (loop/driver / I/O / venue)
```

**FINBAR — backtest** (all bars at once, bar-by-bar loop):

```
   strategy YAML (file/DB)
           |
           v
  +------------------------------+
  | StrategyDefinitionParser     |  [SHARED] already used by both
  | -> definition                |
  | -> primary_required_indicators
  | -> informative_required[h1] |
  | -> required_columns          |
  +------------------------------+
           |
           v
  +----------------------------------------------+
  | MTF ENRICHMENT (currently SPLIT in finbar):   |
  |  compute primary indicators on 30min frame   |  [GAP-1] fold into one
  |  compute info indicators on 1h frame         |  [GAP-1] shared service
  |  merge each info into primary (*_1h cols)    |  [GAP-1] (MultiTimeframe
  |  compute features on merged frame           |  [GAP-1]  BarEnricher)
  |  today: ComputeStrategyIndicatorsUseCase +   |
  |         _prepare_frame + feature calc        |
  +----------------------------------------------+
           |
           v
  +----------------------------------------------+
  | validate_required_data (data-driven warmup)  |  [GAP-1] first row where
  | -> warmup_bars, first_tradable index         |         all required cols
  +----------------------------------------------+         are non-NaN
           |
           v
  +----------------------------------------------+
  | BACKTEST LOOP  (finbar's own driver)         |  [APP] never shared
  |   for each bar:                              |
  |     i < first_tradable -> on_bar() for STATE |  [GAP-1 rule] feed warmup
  |                            (no trade)        |     bars to on_bar;
  |     else:                                    |     finbot doesn't do this
  |       execute pending @ open  -----------+   |
  |       check_exit_conditions -------------+-->|  [GAP-2] IntrabarExitResolver
  |       check_margin_call -----------------|   |  [GAP-2] MarginAccountManager
  |       on_bar(bar, position) -> signal   |   |  [SHARED] JsonRuleBasedStrategy
  |         |                                |   |
  |       PositionSizer -> size -------------|   |  [GAP-2] PositionSizer
  |       PositionOpener -> open            |   |  [GAP-2] PositionOpener/Closer
  |       track equity                       |   |  [GAP-2] ExecutionConfig
  +------------------------------------------|   |
           |                                 |   |
           v                                 |   |
  +------------------------------+          |   |
  | BacktestResultBuilder        |  [APP]   |   |
  | -> trades, equity, metrics   |          |   |
  +------------------------------+          |   |
```

**FINBOT — live trading** (bars arrive via websocket, one at a time):

```
   strategy YAML
           |
           v
  +------------------------------+
  | YamlStrategyDefinitionLoader |  [SHARED] wraps package parser
  | (-> StrategyDefinitionParser)|
  | -> definition + required_ind |
  | -> timeframes (primary+info) |
  +------------------------------+
           |
           v
  +----------------------------------------------+
  | Load warmup HISTORY per interval (REST)      |  [APP] HyperliquidBarSource
  |   primary: load_warmup_bars(30min,100)  OK   |      (data fetch - never
  |   info:    load_warmup_bars(1h,100) DISCARDED!|       shared)
  +----------------------------------------------+
           |
           v
  +-----------------------------+   +-----------------------------+
  | 30min websocket stream      |   | 1h websocket stream         |
  | process_closed_candle(c)    |   | process_informative_candle  |  [APP]
  |         |                   |   |   -> _informative_cache[al] |       (DEAD -
  |         v                   |   |         never read)        |  GAP-1
  |  WarmupWindow.append(c)     |   |                             |
  |  is_ready()? min_bars=20 ---+---+--> FIXED count gate        |  [GAP-1]
  |         | no -> SKIP bar    |   |   (should be data-driven    |  (should use
  |         |   (never calls     |   |    like finbar)             |   validate_
  |         |    on_bar!) WARN  |   +-----------------------------+   required_data)
  |         v yes               |              |
  |  _enrich_bars():            |              |
  |    bars_to_frame(warmup)    |  [SHARED]    |
  |    indicator_calc(PRIMARY   |  [SHARED]    |
  |      ONLY - no merge!) WARN |              |
  |         |                   |    <---------+  (info cache ignored)
  |         v                   |
  |  +----------------------------------------------+
  |  | MultiTimeframeBarEnricher SHOULD go here     |  [GAP-1] the fix:
  |  | (compute info indicators + merge + features) |         compute info
  |  |  - does not exist in finbot today            |         indicators +
  |  +----------------------------------------------+         merge before eval
  |         |                   |
  |         v                   |
  |  enrichment_validator       |  [APP]
  |  .validate(latest, req_cols)|
  |         |                   |
  |         v                   |
  |  evaluator.evaluate --------+--> SharedRuntimeStrategyEvaluator
  |         |                   |   -> package on_bar()  [SHARED]
  |         v                   |      -> SignalDecision
  |    HOLD? ----- yes --> done |
  |         | no                |
  |         v                   |
  |  +----------------------------------------+
  |  | OrderPlanner                           |  [APP]
  |  |  risk gates (live)  keep               |
  |  |  size = default_size = 0.001  WRONG     |  [GAP-2] use shared
  |  |                                        |         PositionSizer
  |  +----------------------------------------+
  |         |                                   |
  |         v                                   |
  |  +--------------------+---------------------+----+
  |  | DRY-RUN / REPLAY   | LIVE                    |  [APP]
  |  | DryRunSubmission   | LiveSubmissionStrategy  |
  |  |  fill @ close      |  -> Hyperliquid REST    |
  |  |  fee = 0   WRONG   |  (real exchange fills)  |
  |  |                    |                         |
  |  | should price via   |  NEVER uses fill model -|
  |  | [GAP-2] closer/    |  exchange is source of  |
  |  | resolver -> matches|  truth (no double-book) |
  |  | backtest exactly   |                         |
  |  +--------------------+-------------------------+
```

The **shared spine** both flows walk (the parity surface):

```
parse -> enrich -> warmup-check -> on_bar() -> [signal]
        [GAP-1]   [GAP-1]        [SHARED]
```

Everything left of `on_bar` is Layer A (Slice 1); everything right is Layer B
(Slice 2). The loop/driver and the venue ([APP]) are never shared.

### Parity is exact for replay, best-effort for live

Because there is no shared loop, parity comes from both loops calling the same
primitives. That makes the guarantee **provable on exactly one path**:

- **Replay / dry-run** — finbot's real loop drives the shared `[GAP-1]` +
  `[GAP-2]` primitives, with a **fake exchange gateway** that fills orders
  using the *same* `[GAP-2]` fill math as the backtest. Decisions, sizing,
  **and** fills all match → **bit-for-bit identical** to a backtest. This is
  what the acceptance test proves.
- **True live on Hyperliquid** — the `[APP]` loop drives the shared `[GAP-1]`
  (decisions) + `[GAP-2]` sizer (sizing), but **fills come from the real
  exchange** (never the fill model). So decisions and sizes match the backtest,
  but PnL is *best-effort* by nature (latency, partial fills, funding skew).
  Finbot's `OrderPlanner` / `LiveSubmissionStrategy` legitimately remain
  separate; there is no shadow bookkeeping.

Stating this explicitly prevents the shared fill math from being mis-sold as a
live-execution guarantee.

### What is already shared today ✅

`on_bar()` — the single line that turns a bar into a long/short/exit signal —
is **already shared** and cannot drift. Finbot imports these 7 package pieces:

| Concern | Package entry point | Finbot adapter |
|---|---|---|
| Parse YAML → `StrategyDefinition` | `StrategyDefinitionParser` | `yaml_strategy_definition_loader.py` |
| Condition evaluation (`on_bar`) → `SignalResult` | `JsonRuleBasedStrategy` (`StrategyDefinitionFactory`) | `shared_runtime_strategy_evaluator.py` |
| Stop/target from `risk:` block | `JsonRiskPriceCalculator` | (feeds the signal) |
| Single-timeframe indicator math | `PandasTaIndicatorCalculator` | `shared_runtime_indicator_calculator.py` |
| Bar ↔ DataFrame | `PandasBarFrameConverter` | `pandas_bar_frame_converter.py` |
| Feature columns | `PandasStrategyFeatureCalculator` | (evaluator path) |
| MTF no-lookahead merge **primitive** | `merge_timeframes` / `PandasTimeframeBarMerger` | ⚠ **finbot never calls it** |

### The two gaps (what is NOT shared, where divergence lives)

**Gap #1 — MTF bar preparation orchestration is not in the package (hard blocker).**
The merge *primitive* is shared, but the orchestration that frames each
timeframe, computes its indicators, merges, then runs features — split across
finbar-the-app's `ComputeStrategyIndicatorsUseCase` (per-TF indicator jobs) and
`BacktestStrategyDefinitionUseCase._prepare_frame()` (merge + features) — is
not. Finbot's `LiveTradingRuntimeUseCase._enrich_bars()` enriches **only the
primary frame**; it populates an `_informative_cache` but never computes
informative indicators and never merges (`grep` for `merge_timeframes` /
`TimeframeBarMerger` across `finbot/` → zero hits). Result: every MTF strategy
produces **zero signals** in finbot, including the production target.

**Gap #2 — The deterministic fill/PnL model is duplicated and divergent.**
Even with Gap #1 fixed so signals fire, finbot's PnL won't match the backtest,
because the execution layer is reimplemented and disagrees:

| Finbar (finbar-the-app) | Finbot today | Divergence |
|---|---|---|
| `PositionSizer`: `size = (equity × risk × leverage) / \|entry−stop\|` | `OrderPlanner` fixed `default_size = 0.001` | 10% risk / 10x → wrong size |
| `IntrabarExitResolver`: gap-aware stop/target on bar H/L | fill at bar `close` only | exits fire at wrong price/bar |
| `LeverageConfig`: liquidation price, stop-vs-liq validation | none | 10x liquidations never modeled |
| `PositionCloser`: gross/net PnL, commission, borrow | `DryRunSubmissionStrategy` fill at `close`, fee = 0 | PnL structurally different |
| Backtest loop: next-bar-open entry (loop-level, app-side) | dry-run/replay entry at same-bar close | replay's fake exchange must replicate next-bar-open to match the backtest |

### Trigger / validation scenario

The motivating test (the one that exposed both gaps): **replay SOL 1h + 30min
data through Finbot's real live pipeline** (mocking only the websocket data
stream), run the production strategy `14_amt_value_reject_30m_1h_mtf.yaml` at
**10% risk / 10x leverage**, and assert the PnL and trade log match the Finbar
backtest. Data exists in `finbar/data/finbar.db` (`price_bar`: SOL, 5008 ×
30min + 5005 × 1h, 2026-03-05 → 2026-06-17).

## Non-Goals

- **Layer C in the package.** No Hyperliquid/SDK/REST/websocket/persistence
  enters `finbar_strategy_runtime`. ADR-2 still forbids it; ADR-6 amends only
  to admit the deterministic fill model (Layer B).
- **backtest↔live exact parity.** The shared fill primitives guarantee
  backtest↔replay parity. Live parity stays best-effort by nature (real exchange fills).
- **A streaming/incremental indicator engine for MTF in this spec.** Slice 1
  uses the existing pandas batch path over the warmup window (the only path
  that supports AMT/VP/market-profile indicators today). A streaming MTF engine
  is tracked separately.
- **>2 informative timeframes.** The package supports up to 3; this spec
  validates with 1 primary + 1 informative. No new timeframe-combinatoric
  logic.
- **New indicators, new metrics, new strategy schema.** No strategy semantics
  change. This is an extraction + sharing effort.
- **Publishing to PyPI.** The package stays in `packages/strategy-runtime/`,
  consumed via the local install finbot already uses. PyPI publish is a later
  concern (per the original extract-package spec).

## Out of scope for this spec (owned elsewhere)

- Finbot's own MTF plumbing spec (`finbot/specs/2026-06-20_multi-timeframe-support/`)
  — it describes how finbot *discovers* timeframes from YAML, warms each, and
  subscribes to streams. This finbar spec defines the **shared enricher** that
  finbot's plumbing will call.

## Decisions baked into this spec

These resolve the five open questions from the original problem statement. Each
is documented as an ADR in `05-architecture.md` so it is auditable and
reversible:

1. **Adopt the three-layer model.** Package owns Layers A + B; Layer C stays in
   finbot. ADR-2 amended by ADR-6 (see `05-architecture.md`).
2. **Parity is exact for replay, best-effort for live.** Finbot's live
   `OrderPlanner` remains separate. (ADR-7.)
3. **Slice 1 uses the batch-on-warmup-window enricher** (pandas path). Streaming
   deferred. (ADR-8.)
4. **Versioning:** Slice 1 → package `0.2.0`; Slice 2 → package `0.3.0`. Finbot
   bumps its pin in lockstep (today `>=0.1.0,<0.2.0`). (ADR-9.)
5. **Ship sliced:** Slice 1 (Layer A) first, Slice 2 (Layer B) next. No
   Slice 3 — the earlier `replay()` facade is dropped (replay must exercise
   finbot's real loop, not a shared runner). (ADR-10, ADR-11.)
