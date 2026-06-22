## Domain Model

### Entities
| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| `IncrementalSessionVpState` | `_bins: dict[float, float]` (price→volume), `_session_date: str` | Accumulates volume per price level within session; on request computes POC/VAH/VAL from distribution | No (in-memory) |
| `BatchedWindowedState` (existing) | `_buffer: deque`, `_names: list[str]` | Single buffer + batch compute for all windowed metrics | No |

### Value Objects
| Name | Fields | Used where |
|------|--------|------------|
| `SessionVpDistribution` | bins: dict, total_volume: float | Internal to IncrementalSessionVpState |
| `VpLevels` | poc: float, vah: float, val: float | Output of distribution materialization |

### Interfaces (for DI)
| Interface | Methods | Implemented by |
|-----------|---------|----------------|
| None new — IncrementalSessionVpState replaces WindowedIndicatorState for VP metrics | `update(bar) → float`, `reset()` | IncrementalSessionVpState |

### Window sizing model
```
_session_count_window(name, interval) → int:
  bars_per_session = 48 (30min crypto) | 24 (1h) | 13 (1h equity)
  lookback = parse N from name (e.g. poc_slope_5 → 5)
  return lookback * bars_per_session
```

### Parallelism model
```
CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(..., parallel=True):
  Run primary engine in main thread
  Run each informative engine in a thread pool
  Merge results after all engines complete
  (Bar feeding must respect chronological order within each engine)
```
