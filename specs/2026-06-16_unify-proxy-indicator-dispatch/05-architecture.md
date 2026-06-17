# Architecture Decisions — Unify Proxy Indicator Dispatch

## ADR-1: Per-handler dispatch with exact request scope

**Context:** Today `calculate(df, ["proxy_vwap"])` returns all 12 proxy
columns via a monolithic `enrich_dataframe_with_proxies` call. This is
surprising (a strategy reading an unrequested proxy "works" by accident),
violates the catalog's "handler presence = computability" invariant, and
makes 3 proxies undiscoverable side-effects.

Options:
- **(A)** Keep the short-circuit but have `enrich_dataframe_with_proxies`
  accept a requested-set and compute only those. Minimal change, but the
  short-circuit remains a special case and the 3 hidden proxies stay
  undiscoverable.
- **(B)** Remove the short-circuit; each proxy dispatches through the
  standard `elif name in _INDICATOR_HANDLERS` path via its own handler.
  Uniform with every other metric; exact request scope for free.

**Decision:** **(B)** — per-handler dispatch with exact request scope.
Confirmed with the user that "request one, get all 12" is unwanted
behaviour.

**Consequences:**
- ✅ The catalog invariant holds universally; `check_metric` is honest by
  construction (Scenario 4).
- ✅ Request scope is predictable; no accidental cross-column reads.
- ✅ Removes the prerequisite wart for the streaming calculator (proxies
  now have real handlers the classifier/windowed-fallback can call).
- ⚠️ Any caller that read an unrequested proxy column must now request it
  explicitly. Audit via `grep -rn "proxy_" tests/ finbar/` (Step 5). One
  known offender: `test_indicator_calculator.py:82`.
- ⚠️ Slightly more work when many proxies are requested together: 12
  handler calls instead of 1 batch call. Negligible (each is a vectorised
  one-liner; the only shared compute — ATR — is cached, see ADR-3).

---

## ADR-2: Keep `enrich_dataframe_with_proxies` off the dispatch hot path but alive

**Context:** `enrich_dataframe_with_proxies` is used by two paths today:
the calculator dispatch (removed by this spec) and
`enrich_bar_with_proxies` (single-bar enrichment, still needed).

**Decision:** Keep the function. Refactor it to delegate to the extracted
per-proxy compute functions (Step 1) so the formulas live in one place.
It is no longer called from `PandasTaIndicatorCalculator`.

**Consequences:**
- ✅ Single source of truth for each proxy formula (handler and batch
  enrichment call the same `compute_proxy_*` function).
- ✅ `enrich_bar_with_proxies` (single-bar) is unchanged.
- ⚠️ Two ways to compute proxies exist (handler-per-column vs batch
  enrich). Acceptable: they share the compute functions, and the batch
  path serves a different consumer (single-bar dicts, not DataFrames).

---

## ADR-3: ATR cluster shares computation via the per-call cache (MACD pattern)

**Context:** Five proxies depend on the Wilder-RMA ATR
(`proxy_atr`, `proxy_ib_high`, `proxy_ib_low`, `proxy_expected_move`,
`proxy_iv`). Under per-handler dispatch, options:
- **(a)** Each recomputes ATR independently — self-contained, but 5× ewm
  when all are requested together.
- **(b)** Each declares `requires={"proxy_atr"}` — creates the
  transitive-dependency problem (dispatch writes NaN when `proxy_atr`
  isn't co-requested; same class as `vol_buffer_high`). Rejected —
  explicitly a Non-Goal.
- **(c)** Compute-if-absent via the per-call `cache` dict, mirroring how
  `macd_signal`/`macd_hist` reuse `cache["macd"]`.

**Decision:** **(c)** — `ensure_proxy_atr(df, cache)` checks
`cache["__proxy_atr"]`; if absent, computes + caches it. All 5 cluster
handlers call it. Each handler is self-contained (works alone, Scenario 5)
AND avoids recompute when co-requested (Scenario 3).

**Consequences:**
- ✅ No request-ordering dependency (Scenario 7 / the Slice-1
  order-independence property still holds — proxies don't touch the
  `atr` column at all now).
- ✅ Matches an established pattern (MACD); no new dispatch mechanism.
- ✅ Streaming will later unify these via shared `AtrState` (the streaming
  MACD pattern from streaming-spec ADR-4) — this batch cache is the
  batch-side analogue.
- ⚠️ The cache key `__proxy_atr` is a private convention; document it at
  the helper. Changing it later is safe (single callsite).

---

## ADR-4: New `MetricFamily.PROXY` to group all 12 proxies together

**Context:** `proxy_typical_price`, `proxy_ohlc4`, `proxy_iv` were
emitted but unregistered. Registering them requires a `MetricFamily`.
Today the registered proxies are scattered across families (spread,
volatility, session, intraday_seasonality); with the 3 hidden ones
added, they'd spread further. The user wants all proxies grouped
together in discovery.

**Decision:** Add a new `MetricFamily.PROXY = "proxy"` and assign **all
12** `proxy_*` metrics to it — including the 9 already-registered ones
(`proxy_atr`, `proxy_vwap`, `proxy_ibs`, `proxy_ib_high`, `proxy_ib_low`,
`proxy_expected_move`, `proxy_parkinson`, `proxy_garman_klass`,
`proxy_rogers_satchell`). `proxy_` is a family in its own right, not just
a confidence level.

**Consequences:**
- ✅ `list_market_metrics(family="proxy")` returns all 12 proxies in one
  call — what a user exploring "what proxy metrics exist" wants.
- ✅ Proxies no longer scatter across spread/volatility/session in the
  unfiltered `list_market_metrics` output; they form one contiguous block.
- ⚠️ The 9 already-registered proxies change family. This is a
  metadata-only change (no formula/dispatch impact), but any caller
  filtering by their old family stops seeing them. Audit via
  `grep -rn 'family.*"spread"\|family.*"volatility"'` for tests that
  count family members — adjust counts.
- ⚠️ The `MetricFamily` enum gains one member. Enum additions are
  backward-compatible (no existing value changes).

---

## ADR-5: Sequencing relative to the streaming-indicator-calculator spec

**Context:** Two specs touch indicator dispatch: this one (proxy routing)
and the streaming calculator (batch vs incremental). They share the
`_handler_registry` as a dependency.

**Decision:** This spec is a **prerequisite** for clean streaming proxy
support, but the two are otherwise independent. Implement this first.
If the streaming spec lands first, proxies resolve to `UNKNOWN`
(fail-closed per streaming-spec ADR-3) or windowed-compute-all-12; this
spec removes that wart by giving each proxy a real handler.

**Consequences:**
- ✅ Streaming's classifier (`classify_indicator`) needs no proxy
  special-case after this spec — proxies are standard handled names.
- ✅ Streaming's windowed fallback ("recompute via the existing batch
  handler on the window slice") works for proxies out of the box.
- 📝 Add a one-line cross-reference in the streaming spec's
  `03-domain.md` classifier section noting the dependency is satisfied.
