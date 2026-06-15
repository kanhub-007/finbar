# Implementation Guide — Single Source of Truth for the Parser Gate

The fix introduces one new file and modifies one existing file plus its
contract tests. The `finbar/` mirror shims re-export automatically.

## Files

| File | Action |
|------|--------|
| `packages/strategy-runtime/finbar_strategy_runtime/parser/usable_metric_set.py` | **CREATE** — the value object |
| `packages/strategy-runtime/finbar_strategy_runtime/parser/unified_metric_catalog.py` | **MODIFY** — replace raw dict fields with `_usable`; rewire 4 methods; add `_validate_consistency()` |
| `packages/strategy-runtime/finbar_strategy_runtime/parser/strategy_indicator_catalog.py` | **MODIFY** — add rolling-VP pattern matching to `resolve()` (ADR-6, INV-7) |
| `packages/strategy-runtime/tests/contract/test_usable_metric_set.py` | **CREATE** — VO unit tests (Scenario 5) |
| `packages/strategy-runtime/tests/contract/test_unified_catalog.py` | **MODIFY** — strengthen name-sync invariant to assert on `resolve()` + agreement; add drift-detection test |
| `packages/strategy-runtime/tests/contract/test_strategy_indicator_catalog.py` | **CREATE** — legacy rolling-VP pattern resolution tests (Scenario 4b) |

No new packages. No interface changes. No parser (`StrategyIndicatorResolver`) changes.

---

### Step 1: Write the failing RED tests first

**File:** `tests/contract/test_usable_metric_set.py` (new) +
`tests/contract/test_unified_catalog.py` (extend with `TestResolveHandlerGate`).

Cover Scenarios 1–5, 7 from `02-scenarios.md`:

- `test_catalogued_handled_metric_resolves` (parametrised) — **fails today**
- `test_every_handler_accepted_by_resolve` — **fails today (116 names)**
- `test_resolve_and_supports_concrete_agree` — **fails today**
- All `UsableMetricSet` unit tests — **fail (import error; class doesn't exist)**

**Verify (RED):**

```bash
cd packages/strategy-runtime
../../.venv/Scripts/python.exe -m pytest tests/contract/test_usable_metric_set.py \
    tests/contract/test_unified_catalog.py::TestResolveHandlerGate -x
```

Expected: collection error for `usable_metric_set` (module missing) and
failures on `resolve`/`agreement` tests.

**Common mistake:** asserting on `supports_concrete()` instead of
`resolve()`. Always assert on `resolve()` — it is the parser's actual
gate. The existing test fell into this trap.

---

### Step 2: Create `UsableMetricSet` (GREEN — Scenario 5)

**File:** `parser/usable_metric_set.py` (new)

A pure, immutable value object. ~45 lines.

```python
"""UsableMetricSet — single source of truth for parser-usable registry metrics.

A metric is usable in a strategy iff it is BOTH catalogued
(``MarketMetricDefinition`` in ``_metric_registry``) AND has a registered
computation handler (``_INDICATOR_HANDLERS``). This value object owns
that rule once, so ``UnifiedMetricCatalog`` cannot re-encode it across
methods (the drift cause of the original ``resolve()`` bug).
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import frozenset


class UsableMetricSet:
    """Immutable view of the registry metrics usable in strategies."""

    def __init__(
        self,
        by_name: Mapping[str, object],
        handled_names: AbstractSet[str],
    ) -> None:
        self._by_name: Mapping[str, object] = dict(by_name)
        self._handled: frozenset[str] = frozenset(handled_names)
        # Compute the usable intersection once (INV-1); cache it (INV: stable).
        self._usable: frozenset[str] = frozenset(
            n for n in self._by_name if n in self._handled
        )

    def resolve(self, name: str) -> str | None:
        """Return ``name`` if usable, else ``None`` (INV-1, INV-5)."""
        n = name.lower()
        return n if n in self._usable else None

    def contains(self, name: str) -> bool:
        """Return True iff ``name`` is usable (INV-1)."""
        return name.lower() in self._usable

    def names(self) -> frozenset[str]:
        """Return the cached usable set (INV-2 single source of truth)."""
        return self._usable

    def __len__(self) -> int:
        return len(self._usable)
```

**Design notes:**
- `dict(by_name)` + `frozenset(...)` defensive-copy the inputs so the VO
  is immutable even if callers later mutate their collections.
- `_usable` is computed in `__init__` and cached; `names()` returns the
  same object on every call (the cache-identity test asserts this).
- Lowercasing matches the parser convention (`_parse_one` lowercases).

**Verify (GREEN for Scenario 5):**

```bash
../../.venv/Scripts/python.exe -m pytest tests/contract/test_usable_metric_set.py -v
```

---

### Step 3: Rewire `UnifiedMetricCatalog` (GREEN — Scenarios 1–4, 6, 7)

**File:** `parser/unified_metric_catalog.py` (modify)

#### 3a. Replace raw dict fields with the value object

In `__init__`, build a `UsableMetricSet` instead of storing `_by_name` /
`_handled_names` directly:

```python
def __init__(self) -> None:
    self._strategy_catalog = StrategyIndicatorCatalog()
    by_name = {m.name: m for m in METRICS + CONCEPTUAL_METRICS}
    import finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator  # noqa: F401
    from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
        _INDICATOR_HANDLERS,
    )
    self._usable = UsableMetricSet(
        by_name=by_name,
        handled_names=_INDICATOR_HANDLERS.keys(),
    )
    self._validate_consistency()
```

**`_by_name` and `_handled_names` are no longer fields.** This is the
structural change that prevents re-encoding the rule.

> ⚠️ `MarketMetricCatalog.get()` / `list()` / `check()` still need
> `_by_name`. Keep a private `_by_name` for THOSE methods (capability
> side), but the **parser-side** methods must go through `_usable`.
> Concretely: store `self._by_name = by_name` for capability queries,
> and `self._usable = UsableMetricSet(by_name, handled)` for the parser
> gate. The parser methods must never touch `_by_name` directly.

#### 3b. Rewire the four parser-side methods

```python
def resolve(self, indicator_type: str, period: int | None) -> str | None:
    name = indicator_type.lower()
    if period is None:
        usable = self._usable.resolve(name)        # single source of truth
        if usable is not None:
            return usable
    return self._strategy_catalog.resolve(indicator_type, period)   # INV-4

def supports_concrete(self, name: str) -> bool:
    if name in self._by_name:
        return self._usable.contains(name)         # single source of truth
    return self._strategy_catalog.supports_concrete(name)

def supported_concrete_names(self) -> list[str]:
    names = set(self._strategy_catalog.supported_concrete_names())
    names.update(self._usable.names())             # single source of truth
    return sorted(names)

def as_dict(self) -> dict:
    payload = self._strategy_catalog.as_dict()
    payload["fixed_indicators"] = sorted(
        set(payload.get("fixed_indicators", [])) | self._usable.names()
    )
    return payload
```

#### 3c. Add the construction-time consistency check (INV-6)

```python
def _validate_consistency(self) -> None:
    """Fail loud if any parser-side method diverges from _usable (INV-6).

    Uses raise (not assert) so it survives ``python -O``. This is the
    backstop that catches drift if a future edit bypasses UsableMetricSet.
    """
    for name in self._usable.names():
        if self.resolve(name, None) != name:
            raise RuntimeError(
                f"UnifiedMetricCatalog.resolve({name!r}) disagrees with "
                f"UsableMetricSet; parser gate is inconsistent."
            )
        if not self.supports_concrete(name):
            raise RuntimeError(
                f"UnifiedMetricCatalog.supports_concrete({name!r}) disagrees "
                f"with UsableMetricSet; parser gate is inconsistent."
            )
```

**Verify (GREEN for all):**

```bash
cd packages/strategy-runtime
../../.venv/Scripts/python.exe -m pytest tests/ -v
```

**Common mistakes:**
- ❌ Reading `_by_name` / `_handled_names` directly inside a parser
  method. ✅ Always go through `self._usable`.
- ❌ Using `assert` for the consistency check. ✅ Use `raise RuntimeError`
  (survives `-O`).
- ❌ Forgetting the `period is None` guard in `resolve`. ✅ Registry
  names take no period; without the guard, a stray period on a registry
  name silently falls through to legacy (which returns None) — harmless
  but obscures intent.

#### 3d. Add rolling-VP pattern matching to the legacy catalog (ADR-6, INV-7)

**File:** `parser/strategy_indicator_catalog.py` (modify)

Add a pattern branch to `StrategyIndicatorCatalog.resolve()` that
mirrors what `supports_concrete()` already performs. After the
`_OPTIONAL_PERIOD_RANGES` check and before the `_FIXED.get(name)`
fallback, recognise the three rolling-VP families and return the name
itself when the window is a positive integer:

```python
def resolve(self, indicator_type: str, period: int | None) -> str | None:
    """Resolve an indicator type/period to a concrete indicator column."""
    name = indicator_type.lower()
    if name in self._PERIOD_RANGES:
        ...  # unchanged
    if name in self._OPTIONAL_PERIOD_RANGES:
        ...  # unchanged
    # Rolling-VP pattern names (vp_poc_10d, rvp_vah_100, cvp_poc_50d, ...)
    concrete = self._match_rolling_vp(name)
    if concrete is not None:
        return concrete
    return self._FIXED.get(name)
```

Extract the matching into a private `_match_rolling_vp(name)` helper so
the same logic is available to `resolve()` (the three families, positive
integer window). Do NOT touch `supports_concrete()` — it already works.

**Verify (GREEN for Scenario 4b):**

```bash
../../.venv/Scripts/python.exe -m pytest tests/contract/test_strategy_indicator_catalog.py -v
```

**Common mistakes:**
- ❌ Refusing to touch the legacy catalog and instead special-casing
  rolling-VP names inside `UnifiedMetricCatalog.resolve()`. ✅ Fix the
  root cause in the legacy catalog; the unified catalog delegates.
- ❌ Accepting window `0` or non-numeric suffixes. ✅ Require a positive
  integer (`>= 1`), exactly as `supports_concrete()` does.
- ❌ Modifying `supports_concrete()` or `_FIXED`. ✅ They already work;
  only `resolve()` was asymmetric.

---

### Step 4: Strengthen the existing invariant test (Scenario 7's "Also test")

**File:** `tests/contract/test_unified_catalog.py`

In `TestNameSyncInvariant::test_every_handler_accepted_by_parser`, add a
`resolve()` assertion alongside the existing `supports_concrete()` one
(see Scenario "Catalog construction fails fast..." Verify block).

**Verify:** full contract suite green.

---

### Step 5: End-to-end smoke (Slice 2 — Scenarios for discovery + VSA strategy)

Run the Scenario "Discovery surfaces handled metrics" and "End-to-end —
a VSA strategy validates" tests, then:

```bash
cd packages/strategy-runtime
../../.venv/Scripts/python.exe -m pytest tests/ -v
cd ../..
.venv/Scripts/python.exe -m pytest tests/ packages/strategy-runtime/tests/ -v
```

Optional MCP integration check: restart the finbar MCP server, call
`validate_strategy_definition` with a YAML referencing `bag_holding`,
confirm `valid: true`. Call `get_strategy_capabilities`, confirm
`bag_holding`, `market_regime`, `bos` appear in `fixed_indicators`.

---

## Common Mistakes Checklist

- ❌ Asserting on `supports_concrete()` only. ✅ Always also assert on `resolve()` (the parser gate).
- ❌ Storing `_handled_names` as a field on the catalog. ✅ Encapsulate it in `UsableMetricSet`.
- ❌ Re-implementing the intersection in `as_dict`. ✅ Reuse `self._usable.names()`.
- ❌ Using `assert` for INV-6. ✅ `raise RuntimeError`.
- ❌ Editing `finbar/` mirror shims. ✅ Edit the package only.
- ❌ Skipping legacy/pattern regression tests (Scenario 4). ✅ Run them — the 4 AMT strategies depend on `_FIXED` + rolling-VP names.
- ❌ Making `UsableMetricSet` implement `IndicatorCapabilityProvider`. ✅ It's a focused collaborator, not a sub-catalog (ISP).

## Recurrence-Prevention Verification

After implementation, to prove the design goal (new metric → auto-wired):

1. Add a throwaway `MarketMetricDefinition(name="zz_smoke")` to `_metric_registry.py`.
2. Register a handler: `@_register("zz_smoke", requires={"close"})` returning a constant.
3. Re-run the suite. `resolve("zz_smoke", None)`, `supports_concrete`,
   `supported_concrete_names`, and `as_dict()["fixed_indicators"]` all
   report it — **without editing any other file**.
4. Remove the throwaway.

This is the contract the "Adding a new metric requires zero catalog-code
changes" scenario codifies.
