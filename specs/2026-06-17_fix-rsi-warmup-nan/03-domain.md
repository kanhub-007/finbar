## Domain Model

### Component Changed

| Component | File | Change |
|-----------|------|--------|
| `_safe_ta(func, *args, **kwargs)` | `indicators/_handler_registry.py:17` | Add warmup masking after result validation |

### Components NOT Changed

| Component | Why unchanged |
|-----------|--------------|
| All 13 handler call sites in `core_ta.py` | They already pass `length=` — picked up automatically |
| `_compute_dynamic` in `_dynamic_dispatch.py` | Also passes `length=period` to `_safe_ta` — picked up automatically |
| `_INDICATOR_HANDLERS` registry | No change |
| `PandasTaIndicatorCalculator.calculate()` | No change |

### New Behavior in `_safe_ta`

```
_safe_ta(func, close, length=14)
    │
    ├── func(close, length=14) returns Series with 0.0 on early bars
    │       │
    │       ▼
    │   result is not None → skip NaN-fill branch
    │       │
    │       ▼
    │   lookback = kwargs.get("length") → 14
    │       │
    │       ▼
    │   len(result) > 14 → True (e.g., 180 bars)
    │       │
    │       ▼
    │   result.iloc[:14] = np.nan   ← NEW: mask first 14 bars
    │       │
    │       ▼
    │   return masked Series
    │
    └── func(close, length=20) returns None (insufficient bars)
            │
            ▼
        Existing NaN-fill branch handles this
```

### Edge Cases

| Case | Behavior |
|------|----------|
| `length` not in kwargs | Mask skipped, original behavior preserved |
| `len(result) <= lookback` | Mask skipped (all bars are within warmup anyway) |
| Function returns None | Existing NaN-fill branch handles it (no change) |
| Function raises exception | Existing except branch handles it (no change) |
| `length=0` or `length=None` | `lookback` is None/0 → mask skipped |
