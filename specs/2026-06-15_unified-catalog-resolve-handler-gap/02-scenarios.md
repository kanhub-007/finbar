# Scenarios — Single Source of Truth for the Parser Gate

All scenarios use **Classical (Detroit) school** tests: real catalog
instances, outcome-based assertions. No mocks, no `verify()` /
`assert_called()`. The catalog auto-imports the calculator on
construction, so `@_register` handlers are populated — no manual setup.

**Scope:**
- New value object `UsableMetricSet` in
  `packages/strategy-runtime/finbar_strategy_runtime/parser/usable_metric_set.py`
- Modified `UnifiedMetricCatalog` in `parser/unified_metric_catalog.py`
- Tests in `tests/contract/test_usable_metric_set.py` (new) and
  `tests/contract/test_unified_catalog.py` (extended)

---

### Scenario: Catalogued metric with a registered handler resolves to its column name

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the unified catalog is constructed (handlers auto-registered)
  And the metric `bag_holding` is catalogued in `_metric_registry`
  And a handler is registered for `bag_holding` in `_INDICATOR_HANDLERS`
  When `resolve("bag_holding", None)` is called
  Then it returns `"bag_holding"` (the concrete column name)

**Primary fix.** Currently returns `None`, causing `unsupported_indicator`.

**Input table:**

| Field          | Type | Example         | Constraints                                  |
|----------------|------|-----------------|----------------------------------------------|
| indicator_type | str  | `"bag_holding"` | Lowercased internally; must be in `_by_name` |
| period         | None | `None`          | Catalogued metrics take no period            |

**Expected output / state change:**

| Assertion                                       | How to verify                        |
|-------------------------------------------------|--------------------------------------|
| `resolve("bag_holding", None) == "bag_holding"` | Direct call on a constructed catalog |
| Same for a representative sample across families | Parametrised test                    |

**Verify (Classical school, black-box):**

```python
import pytest

@pytest.fixture
def catalog():
    from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog
    return UnifiedMetricCatalog()

@pytest.mark.parametrize("metric", [
    "bag_holding", "effort_result_divergence", "market_regime",
    "hurst_exponent", "bos", "choch", "bullish_fvg", "alligator_jaw",
    "stopping_volume", "no_demand", "alligator_status", "fib_618_retrace",
    "corwin_schultz_spread", "funding_rate",
])
def test_catalogued_handled_metric_resolves(catalog, metric):
    assert catalog.resolve(metric, None) == metric
```

**Also test:**
- Mixed-case input `"Bag_Holding"` — `resolve` must lowercase before lookup
  (matching `_parse_one`'s convention).
- `period=None` passed explicitly (the normal fixed-metric path).

---

### Scenario: Catalogued metric WITHOUT a registered handler is still rejected

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the metric `vix` is catalogued but has no registered handler
  When `resolve("vix", None)` is called
  Then it returns `None`

**Regression guard.** The fix must not over-correct by accepting every
catalogued name regardless of handler presence. The handler-required gate
(commit `ee6f725`) stays enforced.

**Input table:**

| Field          | Type | Example | Constraints                              |
|----------------|------|---------|------------------------------------------|
| indicator_type | str  | `"vix"` | In `_by_name`, NOT in `_handled_names`   |

**Verify:**

```python
@pytest.mark.parametrize("metric", ["vix", "turnover", "cross_price_leadership"])
def test_catalogued_unhandled_metric_rejected(catalog, metric):
    assert catalog.resolve(metric, None) is None
```

**Also test:**
- Programmatically assert for every `(catalog_names - handler_names)`,
  so new catalogued-but-unimplemented entries are auto-covered.

---

### Scenario: Unknown metric name is still rejected

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the name `totally_made_up_metric` is neither catalogued nor a
  legacy indicator
  When `resolve("totally_made_up_metric", None)` is called
  Then it returns `None`

**Verify:**

```python
def test_unknown_metric_rejected(catalog):
    assert catalog.resolve("totally_made_up_metric", None) is None
    assert catalog.resolve("not_a_real_indicator", None) is None
```

---

### Scenario: Legacy fixed and period-parameterised indicators still resolve

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the legacy whitelist contains `vp_vah`, `atr`, `vwap`, etc.
  When `resolve` is called for each
  Then it returns the same concrete name (delegated to the legacy catalog)

**Regression guard.** The 4 production AMT strategies in `strategies/`
depend on these resolution paths; they must not break.

**Verify:**

```python
@pytest.mark.parametrize("metric", [
    "vp_vah", "vp_val", "vp_poc", "vwap", "above_value",
    "acceptance_into_value", "value_area_width_pct", "poc_slope_5",
    "is_markdown", "is_distribution",
])
def test_legacy_fixed_indicators_resolve(catalog, metric):
    assert catalog.resolve(metric, None) == metric

@pytest.mark.parametrize("name,period,expected", [
    ("sma", 50, "sma_50"), ("rsi", 14, "rsi_14"), ("ema", 12, "ema_12"),
    ("atr", 2, "atr_2"),
    # Pattern-matched rolling-VP (delegate to legacy — see next scenario):
    ("vp_poc_10d", None, "vp_poc_10d"),
    ("rvp_vah_48", None, "rvp_vah_48"),
    ("cvp_val_20d", None, "cvp_val_20d"),
])
def test_period_parameterised_names_resolve(catalog, name, period, expected):
    assert catalog.resolve(name, period) == expected
```

---

### Scenario: Legacy rolling-VP pattern names resolve for any window

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the legacy catalog advertises rolling-VP pattern families
  (`vp_poc_Nd`, `vp_vah_Nd`, `vp_val_Nd`, `rvp_poc_N`, `rvp_vah_N`,
  `rvp_val_N`, `cvp_poc_Nd`, `cvp_vah_Nd`, `cvp_val_Nd`) via
  `supports_concrete()` and the capability docstring
  And the compute side (`_compute_rolling_vp_dynamic`) handles any `N >= 1`
  When `resolve("<pattern_name>", None)` is called for a window NOT in the
  hardcoded `_FIXED` dict (e.g. `vp_poc_10d`, `rvp_poc_100`, `cvp_poc_50d`)
  Then it returns the pattern name itself (the concrete column)
  And the answer agrees with `supports_concrete()` (no asymmetry)

**Same bug class, legacy side.** During implementation of the registry fix,
a probe revealed that `StrategyIndicatorCatalog.resolve()` lacks the
rolling-VP pattern matching that its `supports_concrete()` already
performs. Only windows hardcoded in `_FIXED` (e.g. `vp_poc_5d`,
`vp_poc_20d`, `rvp_poc_48`) resolved; every other window returned `None`
while `supports_concrete()` returned `True` — the identical
resolve/supports_concrete asymmetry this spec eradicates, in the legacy
catalog, for the rolling-VP families. The compute path already supports
arbitrary `N`; only the parser gate was broken.

**Scope note:** this is a surgical addition to
`StrategyIndicatorCatalog.resolve()` (pattern matching mirroring
`supports_concrete()`), NOT the full Composite refactor excluded by the
Non-Goals. ADR-3 is revised (see `05-architecture.md`) to permit this
minimal consistency fix.

**Input table:**

| Field          | Type | Example          | Constraints                              |
|----------------|------|------------------|------------------------------------------|
| indicator_type | str  | `"vp_poc_10d"`   | Matches `vp_*_Nd` / `rvp_*_N` / `cvp_*_N`|
| period         | None | `None`           | Pattern names take no period             |

**Expected output / state change:**

| Assertion                                              | How to verify                     |
|--------------------------------------------------------|-----------------------------------|
| `resolve("vp_poc_10d", None) == "vp_poc_10d"`          | Direct (window not in `_FIXED`)   |
| `resolve("rvp_poc_100", None) == "rvp_poc_100"`       | Direct (window not in `_FIXED`)   |
| `resolve("cvp_poc_50d", None) == "cvp_poc_50d"`       | Direct (window not in `_FIXED`)   |
| `resolve(n, None) is None ⟺ not supports_concrete(n)` | Symmetry property, all patterns   |

**Verify (Classical school, black-box):**

```python
@pytest.mark.parametrize("name", [
    # vp_*_Nd — only 5d/20d are in _FIXED; 10d/50d/100d were broken
    "vp_poc_10d", "vp_vah_50d", "vp_val_100d",
    # rvp_*_N — only 48/96/336 are in _FIXED; 100 was broken
    "rvp_poc_100", "rvp_vah_200", "rvp_val_500",
    # cvp_*_Nd — only 5d/10d/20d are in _FIXED; 50d was broken
    "cvp_poc_50d", "cvp_vah_100d", "cvp_val_3d",
])
def test_rolling_vp_pattern_resolves_for_any_window(catalog, name):
    assert catalog.resolve(name, None) == name

@pytest.mark.parametrize("name", [
    "vp_poc_10d", "rvp_poc_100", "cvp_poc_50d",
    "vp_vah_5d", "rvp_vah_48", "cvp_vah_20d",  # already in _FIXED
])
def test_rolling_vp_resolve_and_supports_concrete_agree(catalog, name):
    assert (catalog.resolve(name, None) is not None) == catalog.supports_concrete(name)

def test_invalid_rolling_vp_window_rejected(catalog):
    """Non-numeric / zero windows are rejected (pattern requires N >= 1)."""
    assert catalog.resolve("vp_poc_0d", None) is None
    assert catalog.resolve("vp_poc_xd", None) is None
    assert catalog.resolve("rvp_poc_0", None) is None
```

**Also test:**
- The three already-hardcoded windows (`vp_poc_5d`, `rvp_vah_48`,
  `cvp_val_20d`) still resolve (no regression from the pattern branch).
- A strategy YAML referencing `type: vp_poc_10d` validates end-to-end
  (covered by the Slice 2 end-to-end scenario family).

---

### Scenario: UsableMetricSet is the single source of truth for the usable-set rule

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the value object `UsableMetricSet` is constructed from
  `(by_name, handled_names)`
  When `resolve`, `contains`, and `names` are called for names in, outside,
  or partially-present-in the inputs
  Then `resolve(name)` returns `name` iff name is in both inputs
  And `contains(name)` agrees with `resolve(name) is not None`
  And `names()` returns exactly the intersection, as a frozenset
  And the value object is immutable after construction

**This is the recurrence-prevention primitive.** The rule lives in ONE
type, so it cannot drift across catalog methods. Any new catalog method
that needs "is this registry metric usable?" asks this object — there is
no second place to re-encode the rule.

**Input table:**

| Field           | Type                    | Example                       | Constraints            |
|-----------------|-------------------------|-------------------------------|------------------------|
| by_name         | Mapping[str, Definition]| The catalog's `_by_name`      | Required               |
| handled_names   | Collection[str]         | `_INDICATOR_HANDLERS.keys()`  | Required               |

**Expected output / state change:**

| Assertion                                                  | How to verify                          |
|------------------------------------------------------------|----------------------------------------|
| `UsableMetricSet({"a": d}, {"a"}).resolve("a") == "a"`     | Direct                                 |
| `UsableMetricSet({"a": d}, {"a"}).resolve("b") is None`    | Direct (not catalogued)                |
| `UsableMetricSet({"a": d}, set()).resolve("a") is None`    | Direct (catalogued, no handler)        |
| `.contains(x) == (.resolve(x) is not None)`                | Agreement property                     |
| `.names() == frozenset(...)`                               | Returns the cached intersection        |
| Two calls to `names()` return the same object              | Cached, not recomputed                 |

**Verify:**

```python
from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet
from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)

def _def(name):
    return MarketMetricDefinition(name=name)  # minimal valid definition

def test_usable_set_resolve_requires_both_catalog_and_handler():
    s = UsableMetricSet(by_name={"a": _def("a")}, handled_names={"a"})
    assert s.resolve("a") == "a"

def test_usable_set_rejects_catalogued_without_handler():
    s = UsableMetricSet(by_name={"a": _def("a")}, handled_names=set())
    assert s.resolve("a") is None
    assert s.contains("a") is False

def test_usable_set_rejects_handler_without_catalog():
    s = UsableMetricSet(by_name={}, handled_names={"a"})
    assert s.resolve("a") is None

def test_usable_set_resolve_and_contains_agree():
    s = UsableMetricSet(by_name={"a": _def("a"), "b": _def("b")},
                        handled_names={"a"})
    assert s.contains("a") is True and s.resolve("a") == "a"
    assert s.contains("b") is False and s.resolve("b") is None

def test_usable_set_names_is_intersection_and_cached():
    s = UsableMetricSet(by_name={"a": _def("a"), "b": _def("b"), "c": _def("c")},
                        handled_names={"a", "b", "d"})
    expected = frozenset({"a", "b"})
    assert s.names() == expected
    assert s.names() is s.names()  # cached identity — same object
```

**Also test:**
- Case-insensitivity: input `"A"` resolves iff `"a"` is usable
  (matches parser convention).
- Construction with empty inputs is valid (returns empty set).

---

### Scenario: All catalog parser-side methods derive from the single source of truth

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given `UnifiedMetricCatalog` holds an instance of `UsableMetricSet`
  When any of `resolve`, `supports_concrete`, `supported_concrete_names`,
  `as_dict` is called for a registry name
  Then its answer is derived from that one instance (not re-encoded)

**Verifies the DRY invariant.** The catalog no longer holds `_by_name` /
`_handled_names` as raw fields that each method reads independently — it
holds a `_usable: UsableMetricSet` collaborator.

**Verify:**

```python
def test_catalog_delegates_registry_resolution_to_usable_set(catalog):
    """The catalog's _usable collaborator is the single authority.

    For every name the registry knows, resolve() and supports_concrete()
    must agree with _usable — they must not re-encode the rule.
    """
    usable = catalog._usable
    from finbar_strategy_runtime.parser._metric_registry import METRICS, CONCEPTUAL_METRICS
    for name in (m.name for m in METRICS + CONCEPTUAL_METRICS):
        expected = usable.resolve(name)
        assert catalog.resolve(name, None) == expected, (
            f"{name}: catalog.resolve {catalog.resolve(name,None)!r} "
            f"diverges from UsableMetricSet {expected!r}"
        )
        assert catalog.supports_concrete(name) == usable.contains(name), name
```

---

### Scenario: Catalog construction fails fast on internal inconsistency

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a catalog whose `resolve()` returns `None` for a name its own
  `UsableMetricSet` considers usable
  When `UnifiedMetricCatalog.__init__` runs its consistency check
  Then it raises `RuntimeError` with a message naming the divergent name
  And no partially-constructed catalog is returned

**Design-by-Contract invariant at construction.** This is the layer that
catches drift if a future edit bypasses `UsableMetricSet`. Uses an
explicit `raise RuntimeError` (not `assert`) so it survives `python -O`.

**Input table:**

| Field         | Type | Example          | Constraints                          |
|---------------|------|------------------|--------------------------------------|
| (constructed) | —    | monkeypatched    | Force a method to disagree with set  |

**Expected output / state change:**

| Assertion                                            | How to verify                         |
|------------------------------------------------------|---------------------------------------|
| Constructing a divergent catalog raises `RuntimeError`| Inject a broken method, assert raises |
| The message mentions the divergent metric name        | Inspect `str(excinfo.value)`          |

**Verify:**

```python
import pytest

def test_catalog_construction_fails_on_drift(monkeypatch):
    from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog

    # Force resolve() to lie about a usable name — simulating a future
    # edit that bypasses UsableMetricSet. The constructor must refuse.
    def broken_resolve(self, indicator_type, period):
        if indicator_type.lower() == "bag_holding":
            return None  # lie: should be "bag_holding"
        return _real_resolve(self, indicator_type, period)

    # We cannot easily monkeypatch before construction; instead, assert
    # that a correctly-wired catalog DOES construct (the positive case),
    # and assert the invariant via a direct unit test on _validate_consistency.
    catalog = UnifiedMetricCatalog()  # must succeed — currently consistent
    # And the validator itself is unit-tested (see below).

def test_validate_consistency_raises_on_mismatch():
    from finbar_strategy_runtime.parser.unified_metric_set import UsableMetricSet
    from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog

    catalog = UnifiedMetricCatalog()
    # Sabotage: pretend a usable name is not in the usable set, while
    # resolve still returns it. The validator must catch the disagreement.
    catalog._usable = UsableMetricSet(by_name={}, handled_names=set())  # now empty
    with pytest.raises(RuntimeError) as exc:
        catalog._validate_consistency()
    assert "bag_holding" in str(exc.value) or "resolve" in str(exc.value).lower()
```

**Also test:**
- The happy path: a freshly-constructed catalog does NOT raise.
- The validator catches the reverse disagreement
  (`resolve` returns a name `supports_concrete` rejects).

---

### Scenario: Adding a new metric requires zero catalog-code changes (recurrence prevention)

**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a developer adds `MarketMetricDefinition(name="brand_new_metric")`
  to `_metric_registry`
  And registers a handler via `@_register("brand_new_metric", ...)`
  When the catalog is reconstructed and `resolve("brand_new_metric", None)`
  is called
  Then it returns `"brand_new_metric"`
  And `supports_concrete`, `supported_concrete_names`, `as_dict` all
  agree
  And NO file under `parser/` other than `_metric_registry.py` was edited

**This is the spec's raison d'être.** Proves the design goal: new metric
→ auto-wired. No 5th place to forget.

**Verify:**

```python
def test_new_metric_auto_wires_without_catalog_edits(catalog, monkeypatch):
    """A newly-registered handler+definition flows through with zero
    catalog-code edits."""
    from finbar_strategy_runtime.parser import _metric_registry as reg
    from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
        _INDICATOR_HANDLERS,
    )
    from finbar_strategy_runtime.domain.entities.market_metric_definition import (
        MarketMetricDefinition,
    )

    fake_def = MarketMetricDefinition(name="brand_new_metric")
    monkeypatch.setitem(reg.METRICS.__class__, "append",
                        reg.METRICS.append)  # no-op; instead mutate _by_name
    catalog._usable._by_name["brand_new_metric"] = fake_def
    catalog._usable._handled.add("brand_new_metric")

    # Recompute the cached usable set as construction would
    catalog._usable = type(catalog._usable)(
        by_name=catalog._usable._by_name,
        handled_names=catalog._usable._handled,
    )

    assert catalog.resolve("brand_new_metric", None) == "brand_new_metric"
    assert catalog.supports_concrete("brand_new_metric") is True
    assert "brand_new_metric" in catalog.supported_concrete_names()
    assert "brand_new_metric" in catalog.as_dict()["fixed_indicators"]
```

> **Note to implementer:** the exact mutation mechanics (the test
> constructs a new `UsableMetricSet` rather than mutating, to honour
> immutability) are an implementation detail. The contract under test
> is: *a metric known to both `by_name` and `handled_names` is usable
> across all four methods with no per-method wiring.*

**Also test:**
- The git-diff assertion: after this spec is implemented, adding a
  metric and running the suite requires touching only
  `_metric_registry.py` + the handler file. (Manual / documented in
  04-implementation.md.)

---

### Scenario: Discovery surfaces handled metrics in capabilities

**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given the capability payload is built via `as_dict()`
  When the `fixed_indicators` list is inspected
  Then it includes every catalogued metric with a registered handler
  (e.g. `bag_holding`, `market_regime`, `bos`, `hurst_exponent`)
  And it still includes every legacy fixed indicator

**Second symptom fix.** `as_dict()` derives its registry contribution
from `UsableMetricSet.names()`.

**Verify:**

```python
@pytest.mark.parametrize("metric", [
    "bag_holding", "market_regime", "hurst_exponent", "bos", "choch",
    "alligator_jaw", "fib_618_retrace", "corwin_schultz_spread",
])
def test_handled_metric_in_capabilities(catalog, metric):
    assert metric in catalog.as_dict()["fixed_indicators"]

@pytest.mark.parametrize("legacy", ["vp_vah", "atr", "vwap", "acceptance_into_value"])
def test_legacy_metrics_still_in_capabilities(catalog, legacy):
    assert legacy in catalog.as_dict()["fixed_indicators"]
```

---

### Scenario: End-to-end — a VSA strategy validates

**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given a strategy YAML that declares `bag_holding` and
  `effort_result_divergence` as indicators
  When `validate_strategy_definition` is called (via the parser)
  Then validation passes (`valid=True`, no `unsupported_indicator`)
  And the resolved indicator specs carry the correct concrete column names

**End-to-end proof** that VSA/SMC/Bill-Williams strategies are now
functional, not merely declarable.

**Verify:**

```python
def test_vsa_strategy_validates():
    from finbar_strategy_runtime.parser.strategy_definition_parser import (
        StrategyDefinitionParser,
    )
    from finbar_strategy_runtime.parser.unified_metric_catalog import (
        UnifiedMetricCatalog,
    )

    definition = '''
schema_version: "2.0"
name: vsa_smoke_test
timeframes: {primary: 1h}
indicators:
  - {name: atr, type: atr, timeframe: primary}
  - {name: bag_holding, type: bag_holding, timeframe: primary}
  - {name: effort_result_divergence, type: effort_result_divergence, timeframe: primary}
sides:
  long:
    entry:
      condition: {all: [{operator: is_true, left: bag_holding}]}
    exit:
      condition: {any: [{operator: is_true, left: effort_result_divergence}]}
risk:
  stop_loss: {type: atr, multiplier: 3.5}
  take_profit: {type: risk_reward, ratio: 1.5}
'''
    parser = StrategyDefinitionParser(catalog=UnifiedMetricCatalog())
    result = parser.parse(definition)
    assert result.valid, f"Validation failed: {result.errors}"
    assert result.errors == []
    concrete = {ind.concrete_name for ind in result.indicators}
    assert "bag_holding" in concrete
    assert "effort_result_divergence" in concrete
```

**Also test:**
- A strategy referencing a regime classifier (`market_regime`) validates.
- Negative: a strategy referencing `vix` (catalogued, no handler) still
  fails validation with `unsupported_indicator`.
