# Scenarios — Topological Sort for Indicator Dependencies

---

### Scenario: Dependencies resolved regardless of request order
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given ETH-USDC 1h OHLCV bars are available
  When `compute_indicators` is called with indicators in "wrong" order (dependents before their dependencies)
  Then all indicators compute successfully with no `failed_indicators` for dependency-related failures

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| symbol | string | "ETH" | Any cached symbol |
| source | string | "hyperliquid" | Any source |
| interval | string | "1h" | Any intraday interval |
| indicators_json | string[] | ["trend_strength","trend_status","adx","trend_direction","sma_20","sma_50","sma_200"] | Dependents first, deps last |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `trend_strength` column has non-null values after warmup | Inspect bars at page 30+ |
| `trend_status` column has non-null values | Inspect bars at page 30+ |
| `adx` column has non-null values | Inspect bars at page 30+ |
| No "Missing required columns" in `failed_indicators` | Job progress shows empty failed_indicators |
| Result identical to requesting in correct order | Compare output with dependency-first ordering |

**Verify (Classical school, black-box):**
```python
# Request in deliberately wrong order (dependents first)
result_wrong = compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["trend_strength","trend_status","adx","trend_direction","sma_20","sma_50","sma_200"]',
    start_date="2026-06-10")

# Request in correct order (deps first)
result_correct = compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["sma_20","sma_50","sma_200","adx","trend_direction","trend_strength","trend_status"]',
    start_date="2026-06-10")

# Assert both produce identical output columns and values
# Assert result_wrong has NO failed_indicators related to missing columns
```

**Also test:**
- `["breakout_quality","rvol","ibs","breakout_signal","breakout_level","swing_high_20","swing_low_20"]` all work
- `["wyckoff_phase","is_accumulation","profile_shape","atr"]` all work
- `["vol_buffer_high","vol_buffer_low","atr"]` all work

---

### Scenario: No regression for independent indicators
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given any valid OHLCV data
  When `compute_indicators` is called with indicators that have no inter-dependencies
  Then behavior is identical to before the topological sort change

**Verify:**
```python
# Independent indicators (no cross-dependencies)
result = compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["sma_20","rsi_14","macd","vwap","ibs","atr"]',
    start_date="2026-06-10")

# Assert:
# - All 6 columns have non-null values after warmup
# - No failed_indicators
# - Result identical to pre-fix behavior
```

---

### Scenario: Topological sort preserves indicator set
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given any list of indicator names
  When the topological sort is applied
  Then the sorted list contains exactly the same names (no additions, no removals)

**Verify:**
```python
# The sort is a permutation, not a filter
original = ["trend_strength", "adx", "rsi_14", "sma_20"]
sorted_result = topological_sort(original, _INDICATOR_HANDLERS)
assert set(original) == set(sorted_result)
assert len(original) == len(sorted_result)
```

---

### Scenario: Dynamic indicators unaffected by sorting
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a mix of dynamic (parameterized) and static indicators
  When topological sort runs
  Then dynamic indicators (sma_N, rsi_N, etc.) are placed first since they have no inter-indicator dependencies

**Verify:**
```python
# Dynamic indicators have no deps → sort to front
result = compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["trend_direction","sma_20","sma_50","sma_200","rsi_14"]',
    start_date="2026-06-10")

# Assert rsi_14 and sma_* compute before trend_direction
# Assert no failed_indicators
```

---

### Scenario: Deep dependency chain resolves correctly
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given a 4-level dependency chain: `breakout_quality` → `breakout_signal` → `breakout_level` → `swing_high_20`
  When all are requested in reverse order (most-dependent first)
  Then all 7 indicators compute successfully

**Verify:**
```python
# Deep chain in reverse order
result = compute_indicators("ETH", "hyperliquid", "1h",
    indicators_json='["breakout_quality","breakout_signal","breakout_level","swing_high_20","swing_low_20","rvol","ibs"]',
    start_date="2026-06-10")

# Assert:
# - breakout_quality is non-null after warmup
# - breakout_signal is non-null
# - breakout_level is non-null
# - No failed_indicators
```

---

### Scenario: Unknown indicators pass through unchanged
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given a list containing an unknown indicator name
  When topological sort processes it
  Then the unknown name is preserved in the output list and still produces a "Unknown indicator name" failure at computation time

**Verify:**
```python
# Unknown name should not crash the sorter
original = ["nonexistent_indicator", "sma_20", "adx"]
sorted_result = topological_sort(original, _INDICATOR_HANDLERS)
assert "nonexistent_indicator" in sorted_result
```
