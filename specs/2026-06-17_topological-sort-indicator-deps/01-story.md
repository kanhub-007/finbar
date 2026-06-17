# Topological Sort for Indicator Dependency Resolution

## User Story

As a **quantitative trader building multi-indicator strategies**, I want `compute_indicators` to compute my indicators correctly regardless of the order I list them in, so that I don't have to memorize dependency chains or debug silent nulls when my indicators are in the "wrong" order.

## Context

The `PandasTaIndicatorCalculator.calculate()` method iterates through requested indicators in the exact order the user provides. When indicator A depends on indicator B (e.g., `trend_strength` requires `adx`), and A appears before B in the request list, the calculator writes `NaN` for A and records it as `failed_indicators` — even though B IS in the request list and DOES get computed later. There is no retry.

**Real example from MCP audit (2026-06-17, ETH-USDC 1h):**
```
Request: ["sma_20","sma_50","sma_200","trend_direction","trend_strength","trend_status",...]
Result: trend_strength=null, trend_status=null  (because listed before "adx")
But:     adx=24.94  ← computed successfully, just too late!
```

**Affected dependency chains** (all of these fail when ordered incorrectly):

| Dependent | Requires | 
|-----------|----------|
| `trend_direction` | `sma_20`, `sma_50`, `sma_200` |
| `trend_strength` | `adx` |
| `trend_status` | `adx`, `trend_direction` |
| `price_vs_sma20` | `sma_20` |
| `breakout_level` | `swing_high_20` |
| `breakout_signal` | `breakout_level`, `swing_low_20` |
| `breakout_quality` | `rvol`, `ibs`, `breakout_signal` |
| `is_power_zone` | `swing_high_20` |
| `wyckoff_phase` | `profile_shape` |
| `vol_buffer_high` | `atr` |
| `vol_buffer_low` | `atr` |

**Why this matters:** Users requesting e.g. `["wyckoff_phase", "profile_shape", "atr"]` get a working `wyckoff_phase` because the dependency comes first by accident. But `["trend_strength", "adx", "rsi_14"]` silently produces NaN for `trend_strength` because `adx` hasn't been computed yet. The user has no idea why — both indicators ARE in the list.

**The infrastructure already exists:** Every handler registers its dependencies via `@_register(name, requires={...})`. The `_INDICATOR_HANDLERS` dict contains `(handler, requires)` tuples. We just need to sort the request list before iterating.

## Non-Goals

Things explicitly NOT being built in this iteration:
- **Changing the `@_register` API** — the existing `requires` sets are correct; we only change how they're consumed.
- **Adding new dependencies** — if a dependency is missing from the `@_register` decorator, that's a separate bug.
- **Circular dependency detection** — the current dependency graph is acyclic; cycle detection is future work.
- **Parallel execution** — indicators are still computed sequentially; only the order changes.
- **Dynamic indicator dependency tracking** — parameterized indicators (sma_N, rsi_N) have no inter-indicator deps (only OHLCV deps), so they don't need sorting.
