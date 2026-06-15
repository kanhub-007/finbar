# Architecture Decisions — Single Source of Truth for the Parser Gate

## ADR-1: The usable-set rule is a Value Object, not a private helper

**Context:**

The original bug — `resolve()` and `supports_concrete()` disagreeing on
whether `bag_holding` is usable — exists because the rule
*"registry name + handler = usable"* was encoded procedurally in 6
methods of `UnifiedMetricCatalog`, each reading the raw `_by_name` and
`_handled_names` fields independently. Two methods were updated; two
were missed; the bug shipped.

Two design responses were considered:

- **(A) Private helper method** `_usable_registry_names()` on the
  catalog, with every method calling it. ~25 lines, no new file.
- **(B) Value Object** `UsableMetricSet` that owns the rule. ~45 lines,
  one new file.

**Options considered:**

| Criterion | (A) Helper | (B) Value Object |
|---|---|---|
| Removes duplication (DRY) | ✅ | ✅ |
| Rule is testable in isolation | ❌ (needs whole catalog) | ✅ |
| Encapsulates inputs (raw dicts leakable) | ❌ (fields remain on catalog) | ✅ (encapsulated) |
| Prevents re-encoding by structure | ⚠️ (convention only — devs must call helper) | ✅ (rule lives inside a type) |
| Pattern trigger genuinely met | Extract Method (Q8) | Value Object (implicit-concept trigger) |
| Lines added | ~25 | ~45 |
| New files | 0 | 1 |

**Decision:** **(B) Value Object.**

The trigger for the Value Object pattern — *"an implicit domain concept
with multiple behaviours used in multiple places, lacking a first-class
representation"* — is genuinely met: the usable set has three behaviours
(`resolve`, `contains`, `names`) consumed by four catalog methods.
Promoting it to a type means a future contributor adding a 5th method
asks `self._usable` — they cannot re-encode the rule because the logic
is encapsulated inside the VO, not floating as a method they could
bypass. The ~20 extra lines and one file are justified by structural
recurrence prevention, which is this spec's explicit goal.

**Consequences:**

- ✅ Adding a new metric (registry entry + handler) requires ZERO
  catalog-code changes — it flows through `UsableMetricSet` (proven by
  the "zero catalog-code changes" scenario).
- ✅ The rule is unit-testable without constructing the whole catalog
  (no calculator import needed for VO tests).
- ✅ The raw `_by_name` / `_handled_names` fields are removed from the
  catalog, so the drift cause (methods reading them inconsistently) is
  structurally eliminated.
- ⚠️ One new file. Acceptable — it matches the package's existing
  one-class-per-file convention (cf. `StrategyIndicatorCatalog`).

---

## ADR-2: Construction-time consistency check (fail-loud, not fail-silent)

**Context:**

Even with a single source of truth, a future edit could bypass
`UsableMetricSet` (e.g., someone re-introduces a direct `_by_name` read
in `resolve()`). The DRY structure makes this hard to write, but not
impossible. We want drift caught the moment it happens, not when a
regression test happens to run.

**Decision:**

`UnifiedMetricCatalog.__init__` calls `_validate_consistency()`, which
iterates the usable set and asserts `resolve()` and `supports_concrete()`
agree with it for every name. On disagreement it raises `RuntimeError`.

This is the **Design by Contract** pattern: the catalog has an invariant
(its parser-side methods agree), and the invariant is checked at the
boundary where the object becomes observable (construction). A violated
invariant is a programming error, not a runtime condition — so it fails
loud and refuses to hand out a half-valid object.

**Mechanism choice — `raise RuntimeError`, not `assert`:**

`assert` is idiomatic for invariants but is stripped under `python -O`.
For a correctness gate that protects against silent strategy-validation
drift, the check must ALWAYS run. `raise RuntimeError(...)` survives
optimisation and is unambiguous. The trade-off (slightly heavier
construction) is acceptable for a once-per-process object.

**Consequences:**

- ✅ Three layers of defence against recurrence:
  1. **Write-time** — DRY (rule lives in `UsableMetricSet`).
  2. **Construction-time** — `_validate_consistency()` fails the process
     on first import (production, test, REPL) if drift slips through.
  3. **CI-time** — strengthened invariant test catches anything the
     assertion's shape doesn't anticipate.
- ⚠️ Catalog construction does O(n) work over ~210 names. Negligible
  (microseconds, once per process); the current design already iterates
  handlers at import time.

---

## ADR-3: Minimal change — extend, do not fully merge, the catalogs

**Context:**

`StrategyIndicatorCatalog` (the legacy `_FIXED` dict + period-range +
rolling-VP pattern logic) predates unification. A "cleaner" fix would
fold it entirely into `UnifiedMetricCatalog` and delete the legacy
class. That is a larger refactor: the period-resolution logic
(`sma_50`, `vp_poc_10d`, `rvp_vah_48`, `cvp_val_20d`) is non-trivial and
the 4 production AMT strategies in `strategies/` depend on it.

**Decision:**

Do NOT refactor `StrategyIndicatorCatalog`. Keep it as the composed
collaborator for fixed/period/pattern names. Only the registry-side
usable-set rule is promoted to `UsableMetricSet`. `UnifiedMetricCatalog`
now composes **three** focused collaborators: legacy catalog (period &
pattern), `UsableMetricSet` (registry usable set), and `_by_name`
(capability-side metadata for `get`/`list`/`check`).

**Revision (rolling-VP pattern symmetry):** the original decision
assumed the legacy catalog's rolling-VP resolution worked end-to-end.
Implementation revealed that `StrategyIndicatorCatalog.resolve()` lacked
the pattern matching its `supports_concrete()` already performs — so
non-hardcoded windows (`vp_poc_10d`, `rvp_poc_100`, `cvp_poc_50d`)
resolved to `None`. This is the *same* resolve/supports_concrete
asymmetry bug class this spec eradicates, so leaving it unfixed would
contradict the spec's own thesis. ADR-6 therefore permits a **surgical**
addition of rolling-VP pattern matching to the legacy `resolve()`
(mirroring `supports_concrete()`). This is NOT the excluded full
Composite refactor — it is a minimal consistency fix that keeps the
legacy catalog as the composed collaborator.

**Consequences:**

- ✅ Smallest blast radius touching the parser gate; the AMT strategies
  and rolling-VP resolution are preserved (and non-hardcoded rolling-VP
  windows now actually resolve — ADR-6).
- ✅ The fix is reviewable in one sitting (~45 new lines + ~20 rewired
  + ~15 for the legacy pattern branch).
- ⚠️ The "three internal collaborators" smell persists. A future spec
  may consolidate; this spec does not block it.

---

## ADR-6: Surgical rolling-VP pattern matching in the legacy catalog

**Context:**

While implementing the registry fix, a probe of
`StrategyIndicatorCatalog` revealed that `resolve()` returned `None` for
rolling-VP pattern names not hardcoded in `_FIXED` (e.g. `vp_poc_10d`,
`rvp_poc_100`, `cvp_poc_50d`), even though `supports_concrete()` accepted
them and `_compute_rolling_vp_dynamic` computes them for any `N >= 1`.
This is the identical resolve/supports_concrete asymmetry this spec is
eradicating — on the legacy side, for the rolling-VP families.

**Decision:**

Add rolling-VP pattern matching to `StrategyIndicatorCatalog.resolve()`
that mirrors what `supports_concrete()` already does: recognise
`vp_*_Nd`, `rvp_*_N`, `cvp_*_N*Nd` with a numeric window `>= 1` and
return the name itself. This is a ~15-line surgical addition, confined
to the pattern branch of `resolve()`. No other legacy behaviour changes.

**Why not defer to a separate spec:** the spec's thesis is "the parser
gate must not have resolve/supports_concrete asymmetry." Shipping the
registry fix while leaving the legacy asymmetry would be incoherent —
the spec's own strengthened invariant test
(`test_resolve_and_supports_concrete_agree`) would fail for
`vp_poc_10d`. The fix is small, same-class, and required for internal
consistency.

**Consequences:**

- ✅ Every rolling-VP window `>= 1` now resolves and validates
  end-to-end (parser gate + compute path agree).
- ✅ `resolve()` and `supports_concrete()` are symmetric for all pattern
  names — the bug class is eradicated on both sides of the catalog.
- ⚠️ The legacy `resolve()` grows a pattern branch. Acceptable: it
  mirrors an existing branch in `supports_concrete()`, and the
  alternative (a shared private helper) is a trivial later refactor
  that does not change behaviour.

---

## ADR-4: Patterns explicitly considered and rejected

The project's pattern decision tree was walked. The following patterns
had plausible triggers but were rejected as over-engineering for this
specific problem:

| Pattern | Trigger that tempted it | Why rejected here |
|---|---|---|
| **Composite** | The catalog composes two sources (registry + legacy) answering the same interface. | Forcing a registry sub-catalog to implement the full `IndicatorCapabilityProvider` would violate ISP — it cannot meaningfully answer `requires_period` or pattern names. The Value Object is a focused collaborator, not a sub-catalog. |
| **Chain of Responsibility** | `resolve()` tries registry, falls back to legacy. | A 2-step, 3-line fallback is too thin to justify a handler abstraction. A plain `if … else …` fallback is clearer. |
| **Strategy** | Behaviour varies by name source. | Each "strategy" would be ~3 lines; the variation is trivial. |
| **Specification** | The rule is composable (`catalogued AND handled`). | No composition is needed today (single AND). Adding the pattern would be speculative (YAGNI). If future rules need composition (e.g. "AND data class available"), the VO can evolve into a Specification then. |
| **Decorator** | Cross-cutting concern on an interface. | The catalog MERGES two sources; it does not wrap one with a cross-cutting concern. Wrong shape. |

**Applied patterns (final):**
1. **Value Object** — `UsableMetricSet` (primary structural fix).
2. **Single Source of Truth / DRY** — one rule, derived everywhere.
3. **Design by Contract** — `_validate_consistency()` invariant.

---

## ADR-5: The strengthened invariant test is part of the fix

**Context:**

The bug escaped because the existing
`test_every_handler_accepted_by_parser` asserted on `supports_concrete()`
(works) instead of `resolve()` (broken). Same intent, wrong method.

**Decision:**

The fix includes:
1. Strengthening that test to assert on `resolve()` — the actual parser gate.
2. A new agreement test: `resolve()` and `supports_concrete()` must
   return consistent answers for every handler name (INV-3).
3. Parametrised coverage across theory families (VSA, SMC, Bill Williams,
   Fibonacci, regime) so a regression in any family is visible by name.

**Consequences:**

- ✅ The exact bug class cannot recur silently.
- ✅ Future metrics added with handlers are auto-covered by the
  "every handler resolves" invariant (no per-metric test maintenance).
