# Implementation Guide — Topological Sort for Indicator Dependencies

---

### Step 1: Add `_topological_sort` helper function
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/pandas_ta_indicator_calculator.py`

Add a module-level function before the `PandasTaIndicatorCalculator` class. This function is pure — no side effects, no framework dependencies.

```python
from collections import deque

def _topological_sort(
    names: list[str],
    handlers: dict[str, tuple[Callable, set[str]]],
) -> list[str]:
    """Sort indicator names so dependencies precede dependents.
    
    Uses Kahn's algorithm (BFS). Dynamic indicators (not in handlers)
    and those with no inter-indicator dependencies are placed first.
    
    Args:
        names: Requested indicator names in any order.
        handlers: Registry dict mapping name → (handler_fn, requires_set).
    
    Returns:
        Sorted list with the same elements; dependencies before dependents.
    """
    if len(names) <= 1:
        return list(names)
    
    names_set = set(names)
    
    # in_degree counts how many (requested) dependencies remain unsatisfied
    in_degree: dict[str, int] = {name: 0 for name in names}
    adjacency: dict[str, list[str]] = {name: [] for name in names}
    
    for name in names:
        if name not in handlers:
            continue
        _, requires = handlers[name]
        for dep in requires:
            if dep in names_set:
                adjacency.setdefault(dep, []).append(name)
                in_degree[name] = in_degree.get(name, 0) + 1
    
    # Start with all nodes that have no unmet dependencies
    queue: deque[str] = deque(
        name for name in names if in_degree.get(name, 0) == 0
    )
    sorted_names: list[str] = []
    
    while queue:
        node = queue.popleft()
        sorted_names.append(node)
        for dependent in adjacency.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    
    # Append any unprocessed nodes (shouldn't happen with acyclic graph,
    # but handles edge cases like circular deps or unknown names)
    processed = set(sorted_names)
    for name in names:
        if name not in processed:
            sorted_names.append(name)
    
    return sorted_names
```

**Verify:** Import `deque` at top of file; verify no import errors.

---

### Step 2: Wire sort into `calculate()`
**File:** `packages/strategy-runtime/finbar_strategy_runtime/indicators/pandas_ta_indicator_calculator.py`

Change the loop in `calculate()` from:
```python
for name in indicators:
```
to:
```python
sorted_indicators = _topological_sort(indicators, _INDICATOR_HANDLERS)
for name in sorted_indicators:
```

The existing `requires - present_cols` guard remains in place as a safety net for dependencies that aren't in the request list at all.

**Verify:** Run `compute_indicators` with wrong-order request; no "Missing required columns" failures.

---

### Step 3: Run existing tests
**Command:**
```bash
cd packages/strategy-runtime && python -m pytest tests/ -x -q
```

**Common mistake:** Forgetting that `_INDICATOR_HANDLERS` keys are the concrete indicator names (e.g., `"trend_strength"`) while parameterized names (`"sma_20"`) use `_is_dynamic()`. The sort correctly places non-registered names first.

---

### Step 4: Integration test via MCP
**Command:** Use finbar MCP `compute_indicators` with wrong-order request:
```json
["trend_strength","trend_status","adx","trend_direction","sma_20","sma_50","sma_200"]
```

**Verify:**
- No `failed_indicators` for `trend_strength` or `trend_status`
- `trend_strength` has non-null values after warmup
- Result identical to requesting in correct order
