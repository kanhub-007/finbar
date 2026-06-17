# Architecture Decisions — Metric Catalog Bug Fixes

## ADR-1: Fix handlers in-place rather than rewriting dispatch system

**Context:** The indicator dispatch system (`_dynamic_dispatch.py`) resolves dependencies, orders handler execution, and manages cache keys. Several bugs could be fixed by rewriting the dispatch to be more robust. However, the dispatch works correctly for 83% of metrics, and a rewrite risks introducing new regressions across all 200+ metrics.

**Decision:** Fix individual handlers in-place (arg mismatches, window sizes, dependency declarations) rather than rewriting the dispatch core.

**Consequences:**
- ✅ Lower risk — each fix is isolated to one handler or one utility function
- ✅ Faster delivery — 1-line fixes vs. multi-day rewrite
- ⚠️ Future bugs of the same class (arg mismatch, window mismatch) won't be prevented automatically
- ⚠️ Still need to address root cause prevention (Step 8: MCP tool enhancement)

---

## ADR-2: Compute missing proxies inside enrich_dataframe_with_proxies (Option B)

**Context:** The original plan proposed making `enrich_dataframe_with_proxies` operate in-place to fix proxy column loss. Verification revealed the proxy handlers in `inside_bar.py` are NEVER dispatched — a `name.startswith("proxy_")` short-circuit in `pandas_ta_indicator_calculator.py` routes all proxy names directly to `enrich_dataframe_with_proxies`. The handlers are dead code; their only effect is to make `check_metric` lie.

Three options considered:
- (A) Remove the short-circuit so proxy handlers dispatch normally, then make each self-contained.
- (B) Add the missing proxy computations directly to `enrich_dataframe_with_proxies`; delete dead handlers.
- (C) Keep status quo and just document the limitations.

**Decision:** Option B.

**Consequences:**
- ✅ ~10-line change to one function; matches the actual execution path.
- ✅ Removing dead handlers makes `check_metric` honest (no more "computable" lies for `proxy_atr`).
- ✅ `proxy_atr` is always computed, so `proxy_ib_high/low/expected_move` always work unconditionally.
- ⚠️ Proxy metrics remain a special case in the dispatch (the `name.startswith("proxy_")` branch). If a future proxy metric needs per-bar rolling logic that doesn't fit `enrich_dataframe_with_proxies`, Option A becomes necessary.
- 📝 The short-circuit itself is a code smell — a follow-up ticket should consider unifying proxy dispatch with the normal handler path (Option A) once the immediate bugs are fixed.

---
## ADR-6: Surface handler exceptions instead of silently converting to NaN

**Context:** `pandas_ta_indicator_calculator.py` catches every handler exception and writes `result[name] = np.nan` with only a `logger.warning`. This is the structural reason every bug in this spec went undetected: the `demand_zone_score` TypeError, the AMT intraday exception, and (originally) the proxy handler issues all produced silent nulls instead of visible errors. Users and the LLM cannot distinguish "metric legitimately returned NaN during warmup" from "metric crashed.".

**Decision:** Keep the try/except (a single bad metric must not abort the whole job) but collect failures into a `failed_indicators` list exposed in job metadata, so `get_indicator_job_progress` and `get_indicator_job_results` surface them.

**Consequences:**
- ✅ Highest-leverage fix for future bug detection — silent nulls become visible errors.
- ✅ Backwards-compatible: existing NaN behaviour preserved for consumers that only read columns.
- ⚠️ Slightly more work for the job runner (must thread the `failed` list through to result metadata).
- ⚠️ Does not prevent bugs — only makes them visible. Still need the constraint-metadata work (ADR-5) for `check_metric` to warn proactively.

---

## ADR-3: Compose `rolling_scalar_series` window from function defaults

**Context:** 4 handlers call `rolling_scalar_series(calculator, series)` with default `window=20`, but the calculator functions have `lookback=60` or `lookback=21`. This silent mismatch causes all-null output. Alternatives: (a) hardcode correct window per handler, (b) introspect function signature defaults.

**Decision:** Hardcode correct window per handler for now (quick fix). Add a code comment flagging each callsite for future introspection-based auto-detection.

**Consequences:**
- ✅ Immediate fix — handlers produce correct output
- ⚠️ If a function's default lookback changes, the hardcoded window must be updated manually
- ⚠️ Future new handlers may repeat the same mistake
- 📝 Mitigation: Add lint rule or test that verifies `rolling_scalar_series` window >= function's internal lookback

---

## ADR-4: Proxy `first_last_hour_vol_fraction` from intraday grouping

**Context:** The metric requires `opening_volume` and `closing_volume` columns that no data source provides. Alternatives: (a) remove the metric entirely, (b) mark as permanently unavailable, (c) implement a proxy from intraday bar grouping.

**Decision:** Implement a proxy that groups intraday bars by UTC date and sums volume for the first and last hour. On daily data, return NaN.

**Consequences:**
- ✅ Keeps the metric alive and useful for intraday users
- ✅ Provides meaningful signal (U-shaped volume curves are well-studied in market microstructure)
- ⚠️ The proxy assumes UTC day boundaries — not aligned with exchange local time (NYSE 9:30–16:00 ET)
- ⚠️ On crypto (24/7), "first/last hour" is arbitrary — but still captures intraday volume patterns
- 📝 Document the UTC-day assumption in catalog

---

## ADR-5: Add constraint metadata to metric registry

**Context:** `check_metric` and `list_market_metrics` currently only check handler existence and OHLCV column availability. They don't report bar-count requirements, data-class restrictions, or condition notes. This causes users to request metrics that silently fail.

**Decision:** Add optional `bar_requirement`, `data_class_requirement`, and `condition_note` fields to the metric registry. Expose them in `list_market_metrics` and `check_metric` responses.

**Consequences:**
- ✅ Users get actionable warnings before running compute jobs
- ✅ LLM-based strategy authors can check constraints programmatically
- ⚠️ Requires updating ~15 metric entries in `_metric_registry.py`
- ⚠️ Doesn't prevent the bug — just warns. The execution-time fix (Steps 1-4) is still needed for correctness
