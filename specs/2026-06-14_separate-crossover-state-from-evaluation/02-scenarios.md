# Scenarios — Separate Crossover State from Boolean Evaluation

All scenarios use Classical-school, black-box tests: real `ConditionEvaluator` instances, synthetic bars, and assertions on outcomes (boolean results + crossover state). No mocks, no interaction assertions.

---

### Scenario: Crossover state recorded even when `all` group short-circuits on first False
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a condition group `all: [volume > 500, sma_20 crosses_above sma_50]`
  And a bar where volume=100 (first child is False)
  When the group is evaluated
  Then the boolean result is False
  And the crossover state `(99, 100)` is recorded in pending_values for key `sma20:sma50:crosses_above`

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bar | dict | `{"sma_20": 99, "sma_50": 100, "volume": 100}` | Enriched OHLCV bar |
| group | ConditionGroup | `all: [volume>500, crosses_above(sma_20, sma_50)]` | First child False |
| previous_values | dict | `{}` | Empty on first bar |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `result == False` | `all` group with first child False |
| `pending_values["sma20:sma50:crosses_above"] == (99.0, 100.0)` | State recorded despite short-circuit |

**Verify (Classical school, black-box):**
```python
evaluator = ConditionEvaluator()
pv: dict = {}

entry = _make_all_group(
    _vol_gt(500),           # first child: False
    _crosses_above("sma_20", "sma_50"),  # second child: would record state
)

bar = {"sma_20": 99, "sma_50": 100, "volume": 100}
result = evaluator.evaluate(entry, bar, pv)

assert result is False
assert pv.get("sma20:sma50:crosses_above") == (99.0, 100.0)
```

**Also test:**
- Crossover as first child, volume as second child — both still evaluated
- Three children, first and third are crossovers, middle False — all three evaluated
- `not` group around a crossover — state still recorded

---

### Scenario: Crossover state recorded even when `any` group short-circuits on first True
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a condition group `any: [rsi < 30, sma_20 crosses_above sma_50]`
  And a bar where rsi=25 (first child is True)
  When the group is evaluated
  Then the boolean result is True
  And the crossover state is STILL recorded for all crossover children

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bar | dict | `{"sma_20": 99, "sma_50": 100, "rsi_14": 25}` | First child True |
| group | ConditionGroup | `any: [rsi<30, crosses_above(sma_20, sma_50)]` | Short-circuits on first |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `result == True` | `any` with first child True |
| `pending_values` contains crossover key | State recorded despite short-circuit |

**Verify (Classical school, black-box):**
```python
evaluator = ConditionEvaluator()
pv: dict = {}

entry = _make_any_group(
    _rsi_lt(30),            # first child: True → short-circuit
    _crosses_above("sma_20", "sma_50"),  # must still record state
)

bar = {"sma_20": 99, "sma_50": 100, "rsi_14": 25}
result = evaluator.evaluate(entry, bar, pv)

assert result is True
assert pv.get("sma20:sma50:crosses_above") == (99.0, 100.0)
```

**Also test:**
- Multiple crossovers in `any` group, first child True — all crossovers recorded
- `any` group where no child is True — all children evaluated fully (no short-circuit)

---

### Scenario: Two-bar crossover sequence works identically to current eager evaluation
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given an `all` group containing a crossover and a separate filter condition
  When two bars are evaluated in sequence with the filter failing on bar 1 and passing on bar 2
  Then bar 1 records crossover state and bar 2 detects the crossover (identical to current behaviour)

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bar1 | dict | `{"sma_20": 99, "sma_50": 100, "volume": 100}` | Filter fails |
| bar2 | dict | `{"sma_20": 101, "sma_50": 100, "volume": 2000}` | Filter passes, crossover triggers |
| previous_values | dict | `{}` | Shared across both calls |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| Bar 1: result == False, pv has crossover state | Filter False, state recorded |
| Bar 2: result == True | Filter True + crossover detects transition |

**Verify (Classical school, black-box):**
```python
evaluator = ConditionEvaluator()
pv: dict = {}

entry = _make_all_group(
    _vol_gt(500),
    _crosses_above("sma_20", "sma_50"),
)

bar1 = {"sma_20": 99, "sma_50": 100, "volume": 100}
r1 = evaluator.evaluate(entry, bar1, pv)
assert r1 is False
assert "sma20:sma50:crosses_above" in pv

bar2 = {"sma_20": 101, "sma_50": 100, "volume": 2000}
r2 = evaluator.evaluate(entry, bar2, pv)
assert r2 is True   # crossover detected because bar1 recorded state
```

**Also test:**
- Same sequence with `any` group instead of `all`
- Three-bar sequence where crossover only triggers on bar 3
- Multiple crossovers in nested groups — state accumulates correctly

---

### Scenario: Nested groups propagate crossover state from all levels
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a deeply nested condition tree with crossovers at multiple levels
  When the tree is evaluated
  Then crossover state is recorded for ALL crossover conditions regardless of nesting depth

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bar | dict | Enriched bar | Contains all referenced columns |
| group | ConditionGroup | `any: [all: [cross_a, cross_b], vol > 500]` | Nested crossovers |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| All crossover keys present in pv | Inspect pv keys |
| Boolean result matches eager evaluation | Compare with reference |

**Verify (Classical school, black-box):**
```python
evaluator = ConditionEvaluator()
pv: dict = {}

inner = _make_all_group(
    _crosses_above("fast", "slow"),
    _crosses_below("rsi", "threshold"),
)
outer = _make_any_group(inner, _vol_gt(500))

bar = {"fast": 10, "slow": 20, "rsi": 70, "threshold": 50, "volume": 100}
result = evaluator.evaluate(outer, bar, pv)

assert pv.get("fast:slow:crosses_above") == (10.0, 20.0)
assert pv.get("rsi:threshold:crosses_below") == (70.0, 50.0)
```

**Also test:**
- `not` wrapping a crossover — state still recorded
- `not` wrapping `any` containing crossovers — all recorded
- Depth 5 nesting (max allowed) — all crossovers recorded

---

### Scenario: Short-circuit avoids unnecessary non-crossover evaluations
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given an `all` group where the first child is a pure boolean False
  When the group is evaluated
  Then non-crossover children after the first False are NOT evaluated
  But crossover children ARE evaluated for state tracking

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bar | dict | `{"close": 50}` | Simple bar |
| group | ConditionGroup | `all: [close < 40, vol > 500, rsi < 30]` | No crossovers |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `result == False` | First child fails |
| Only first child evaluated | Can verify via coverage or side-effect counter |

**Verify (Classical school, black-box):**
```python
evaluator = ConditionEvaluator()
pv: dict = {}

# Use a call counter to verify evaluation count
call_count = 0
def _counting_handler(df, name, cache):
    nonlocal call_count
    call_count += 1
    return df

# Register a test indicator that counts calls
# (In practice, verify by checking that expensive pure-boolean
#  children are skipped when short-circuit determines the result)

entry = _make_all_group(
    _cond("close", "<", 40),    # False → short-circuit
    _cond("volume", ">", 500),  # should NOT be evaluated
    _cond("rsi_14", "<", 30),   # should NOT be evaluated
)

bar = {"close": 50, "volume": 100, "rsi_14": 50}
result = evaluator.evaluate(entry, bar, pv)

assert result is False
# Only the first child was evaluated; second and third were short-circuited
```

**Also test:**
- `any` group, first child True → remaining non-crossover children skipped
- Mixed group with crossover in position 3 — children 1-2 can short-circuit, child 3 (crossover) always evaluated

---

### Scenario: Existing test suite passes with zero regressions
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the refactored ConditionEvaluator
  When the full Finbar test suite and strategy-runtime contract tests are run
  Then all tests pass with identical results to the current eager-evaluation implementation

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| 459 Finbar tests pass | `pytest tests/` |
| 68 package contract tests pass | `pytest packages/strategy-runtime/tests/` |
| `test_crossover_state_updates_when_prior_all_condition_is_false` passes | Specific regression test |

**Verify:**
```bash
pytest tests/ -q
pytest packages/strategy-runtime/tests/ -q
```
