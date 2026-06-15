# Domain Model — Single Source of Truth for the Parser Gate

## Ubiquitous Language

| Term | Definition |
|------|------------|
| **Catalogued metric** | A metric with a `MarketMetricDefinition` entry in `_metric_registry.py`. |
| **Handled metric** | A metric with a registered computation function in `_INDICATOR_HANDLERS` (via `@_register`). |
| **Usable metric** | A metric that is BOTH catalogued AND handled. This is the set a strategy may reference. |
| **Usable set** | The immutable value object (`UsableMetricSet`) that owns the usable-set rule. Single source of truth. |
| **Parser gate** | `UnifiedMetricCatalog.resolve(indicator_type, period)`. The strategy parser rejects any indicator whose `resolve()` returns `None`. |
| **Handler-required gate** | The invariant: a catalogued metric is accepted by the parser **iff** it has a registered handler. (Commit `ee6f725`.) |
| **Consistency invariant** | `resolve()`, `supports_concrete()`, `supported_concrete_names()`, and `as_dict()["fixed_indicators"]` must all derive from the same `UsableMetricSet` and therefore agree for every name. |
| **Legacy fixed indicator** | An indicator in `StrategyIndicatorCatalog._FIXED` — the pre-unification whitelist (~95 names). |

## Entities / Value Objects

### NEW: `UsableMetricSet` (Value Object)

| Field | Type | Behaviour | Persisted? |
|-------|------|-----------|------------|
| `_by_name` | `Mapping[str, MarketMetricDefinition]` (stored reference) | Source 1 of the rule | No |
| `_handled_names` | `Collection[str]` (stored reference) | Source 2 of the rule | No |
| `_usable` (cached) | `frozenset[str]` | The intersection, computed once | No |

**Methods:** `resolve(name) -> str | None`, `contains(name) -> bool`,
`names() -> frozenset[str]`.

**Purity:** immutable after construction. No framework, I/O, or global
state. Unit-testable with zero infrastructure.

**Location:** `packages/strategy-runtime/finbar_strategy_runtime/parser/usable_metric_set.py` (new file).

### MODIFIED: `UnifiedMetricCatalog`

| Field | Type | Behaviour | Persisted? |
|-------|------|-----------|------------|
| `_strategy_catalog` | `StrategyIndicatorCatalog` (legacy) | Owns fixed + period + pattern resolution (unchanged) | No |
| `_usable` | `UsableMetricSet` | **NEW.** Owns the registry usable-set rule | No |

**Removed fields:** `_by_name`, `_handled_names` — these raw dicts are
encapsulated inside `_usable` so catalog methods can no longer read them
independently (the drift cause).

**Location:** `packages/strategy-runtime/finbar_strategy_runtime/parser/unified_metric_catalog.py` (modified).

## Interfaces (for DI)

| Interface | Methods (relevant) | Implemented by | Used by |
|-----------|--------------------|----------------|---------|
| `IndicatorCapabilityProvider` | `resolve`, `supports_concrete`, `as_dict`, ... | `UnifiedMetricCatalog` (unchanged contract) | `StrategyIndicatorResolver`, `StrategyCapabilityService` |
| `MarketMetricCatalog` | `check`, `get`, `list`, `resolve_best` | `UnifiedMetricCatalog` (unchanged contract) | `check_metric_capability`, capability endpoints |

**No new interfaces. No interface changes.** `UsableMetricSet` is an
internal collaborator of `UnifiedMetricCatalog`, not part of any public
contract — it has no interface of its own (it has one implementation,
one responsibility, and is consumed by exactly one class; an interface
would be speculative per YAGNI / ISP).

## Invariants

### INV-1: Handler-required parser gate (correctness)

> A catalogued metric MUST be accepted by `resolve()` (return its own
> name) **iff** it has a registered handler in `_INDICATOR_HANDLERS`.

**Enforcement:** `UsableMetricSet.resolve()` — the rule is encoded once.

### INV-2: Single source of truth (recurrence prevention — NEW)

> Every catalog method that answers "is this registry metric usable?"
> MUST derive its answer from the single `_usable: UsableMetricSet`
> instance. No method may re-encode the usable-set rule by reading
> `_by_name` / `_handled_names` directly.

**Enforcement:** structural — the raw dicts are no longer fields on the
catalog; they live inside `UsableMetricSet`. A method that needs the
rule must call `self._usable.resolve(name)`.

### INV-3: Method agreement

> For every metric name: `resolve(n,None) is not None` ⟺
> `supports_concrete(n)` ⟺ `n in supported_concrete_names()` ⟺
> `n in as_dict()["fixed_indicators"]` (for registry names).

**Enforcement:** INV-2 makes this a corollary (all derive from the same
set), AND `_validate_consistency()` asserts it at construction as a
backstop.

### INV-4: Legacy delegation preserved

> Period-parameterised indicators (`sma_50`, `atr_2`) and rolling-VP
> pattern names (`vp_poc_10d`, `rvp_poc_48`, `cvp_vah_20d`) MUST
> continue to resolve via the legacy catalog.

**Enforcement:** the fallback branch of `resolve()` after the
`UsableMetricSet` check returns None or not-applicable.

### INV-5: Unhandled catalogued metrics remain rejected

> A catalogued metric WITHOUT a handler (e.g. `vix`, `turnover`,
> `elliott_wave`) MUST return `None` from `resolve()`.

**Enforcement:** `UsableMetricSet.resolve()` requires membership in
BOTH `_by_name` AND `_handled_names`.

### INV-6: Construction-time consistency (fail-loud — NEW)

> `UnifiedMetricCatalog.__init__` MUST call `_validate_consistency()`,
> which raises `RuntimeError` if any parser-side method disagrees with
> `_usable` for any catalogued metric name.

**Enforcement:** Design by Contract. Uses `raise RuntimeError` (not
`assert`) so it survives `python -O`. The catalog must never enter a
state where its methods disagree — that is the exact bug class being
eradicated.

### INV-7: Legacy rolling-VP pattern resolution symmetry (NEW)

> For every rolling-VP pattern name (`vp_*_Nd`, `rvp_*_N`, `cvp_*_Nd`
> with `N >= 1`), `StrategyIndicatorCatalog.resolve(name, None)` MUST
> return `name`, and MUST agree with `supports_concrete(name)`. Only
> windows previously hardcoded in `_FIXED` resolved; the pattern branch
> closes the asymmetry for every other window.

**Enforcement:** `StrategyIndicatorCatalog.resolve()` performs the same
rolling-VP pattern matching that `supports_concrete()` already performs
(vp/rvp/cvp prefix + numeric window). The compute side
(`_compute_rolling_vp_dynamic`) already accepts any `N >= 1`, so this is
purely a parser-gate consistency fix — the same resolve/supports_concrete
asymmetry bug class, on the legacy side.

**Scope:** a surgical pattern-matching addition to the legacy `resolve()`.
It does NOT refactor `StrategyIndicatorCatalog` (ADR-3 revised in
`05-architecture.md` to permit this minimal consistency fix).

## Lifecycles

Not applicable. `UnifiedMetricCatalog` and `UsableMetricSet` are
stateless services constructed once per process (handlers auto-register
at import time). `UsableMetricSet` is immutable after construction.

## Relationships

```
StrategyIndicatorResolver ──uses──▶ IndicatorCapabilityProvider (resolve)
        │                                      ▲
        │                              UnifiedMetricCatalog (unchanged contract)
        │                                      │  composes:
        ▼                                      ├── _usable : UsableMetricSet   ◀── NEW (owns rule)
  parse() → IndicatorSpec[]                    │      ├── _by_name    ← _metric_registry.py
        │                                      │      └── _handled    ← _INDICATOR_HANDLERS
        ▼                                      └── _strategy_catalog (legacy: fixed + period + pattern)
  StrategyValidationError (if resolve() returns None)
```

## Pattern Application (from the 21-pattern decision tree)

| Pattern | Applied? | Rationale |
|---|---|---|
| **Value Object** | ✅ `UsableMetricSet` | An implicit domain concept (the usable set) with multiple behaviours (resolve / contains / names) used in multiple places. Promoting it to an immutable VO removes duplication and encapsulates the rule. |
| **Single Source of Truth** | ✅ | The rule is computed once in `UsableMetricSet`; all catalog methods delegate. (This is the structural fix; DRY is the principle.) |
| **Design by Contract** | ✅ `_validate_consistency()` | Runtime invariant check at construction; fail-loud if any method drifts from the set. |
| Composite | ❌ rejected | Forcing a registry sub-catalog to implement the full `IndicatorCapabilityProvider` would violate ISP (it can't answer period/pattern questions). The VO is a focused collaborator, not a sub-catalog. |
| Chain of Responsibility | ❌ rejected | The fallback from registry→legacy is a 2-step, 3-line dispatch — too thin to justify a handler abstraction. |
| Strategy / Specification | ❌ rejected | Overkill — each "strategy"/"spec" would be trivial, and no composition is needed. |
| Decorator | ❌ rejected | The catalog MERGES two sources; it does not wrap one with a cross-cutting concern. |

## Entity vs ORM separation

Not applicable — no persistence layer involved. All types are pure
in-memory domain objects.
