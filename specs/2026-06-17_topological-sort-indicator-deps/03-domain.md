## Domain Model

### Existing Components (no changes)

| Component | Location | Role |
|-----------|----------|------|
| `_INDICATOR_HANDLERS` | `indicators/_handler_registry.py` | Dict mapping indicator name → `(handler_fn, requires_set)`. Already populated at import time. |
| `PandasTaIndicatorCalculator.calculate()` | `indicators/pandas_ta_indicator_calculator.py` | Single-pass loop over indicators. Writes NaN on missing deps. |
| `@_register(name, requires={...})` | Various handler modules | Decorator registering each handler with its dependency set. |

### New Component

| Component | Location | Role |
|-----------|----------|------|
| `_topological_sort(indicators, handlers)` | `indicators/pandas_ta_indicator_calculator.py` (module-level helper) | Sorts indicator list so dependencies precede dependents. |

### Algorithm — Kahn's Algorithm (BFS-based topological sort)

```
Input:  names: list[str] — requested indicator names
        handlers: dict[name → (fn, requires_set)] — the registry

Output: sorted_names: list[str] — names in dependency order
        (independent indicators first, most-dependent last)

1. Build in-degree map and adjacency list:
   - For each name in names:
       if name in handlers:
           for each dep in handlers[name].requires:
               if dep in names_set:         # only track deps that are also requested
                   adjacency[dep].append(name)
                   in_degree[name] += 1
   
2. Initialize queue with all names where in_degree == 0
   (these have no unmet dependencies within the request set)

3. While queue is not empty:
       node = queue.pop(0)
       sorted_names.append(node)
       for each dependent in adjacency[node]:
           in_degree[dependent] -= 1
           if in_degree[dependent] == 0:
               queue.append(dependent)

4. Append any remaining names (unknowns, circular deps) to preserve them

5. Return sorted_names
```

### Integration Point

In `PandasTaIndicatorCalculator.calculate()`, replace:
```python
for name in indicators:
```
with:
```python
sorted_indicators = _topological_sort(indicators, _INDICATOR_HANDLERS)
for name in sorted_indicators:
```

Everything else remains unchanged — the `requires - present_cols` check still runs (as a safety net for dependencies not in the request list), and the per-handler cache still works.

### Edge Cases

| Case | Handling |
|------|----------|
| Indicator not in `_INDICATOR_HANDLERS` (dynamic/unknown) | in_degree = 0 → placed first |
| Dependency not in request list | Ignored for sorting (the existing `requires - present_cols` check catches it at runtime) |
| Circular dependency | Kahn's algorithm leaves unprocessed nodes; fall back to original order for those |
| Empty indicator list | Short-circuit before sort |
| All independent indicators (no deps) | Sort is a no-op (all in_degree = 0) |
