## Domain Model

### Components Changed

| Component | File | Change |
|-----------|------|--------|
| `hurst_exponent(min_bars=...)` default | `domain/services/hurst_regime.py:16` | `100` → `250` |
| `fractal_regime(min_bars=...)` default | `domain/services/hurst_regime.py:97` | `100` → `250` |
| `MarketMetricDefinition.min_lookback` | `parser/_metric_data.py:988` | `100` → `250` |
| `MarketMetricDefinition.condition_note` | `parser/_metric_data.py:990` | `"100"` → `"250"` |

### Components NOT Changed

| Component | Why unchanged |
|-----------|--------------|
| R/S algorithm (`for lag in lags` loop) | Correct — only the guard threshold changes |
| `broadcast_scalar_over_series` | Already handles `None` → NaN correctly |
| `_h_hurst` handler in `price_action.py` | Calls `_hurst(df["close"])` — picks up new default automatically |
| `_h_frac_regime` handler | Calls `_frac_regime(df["close"])` — picks up new default automatically |
| `fractal_regime` return values | Returns `"unknown"` when H is None (already correct) |

### Data Flow

```
User requests "hurst_exponent"
    │
    ▼
PandasTaIndicatorCalculator.calculate()
    │
    ▼
_h_hurst(df, _name, _cache)           ← price_action.py:430
    │
    ▼
broadcast_scalar_over_series(_hurst, df["close"])
    │
    ▼
hurst_exponent(close, min_bars=250)   ← hurst_regime.py (NEW DEFAULT)
    │
    ├── len(close) < 250 → None
    │       │
    │       ▼
    │   broadcast_scalar_over_series: None → NaN Series
    │
    └── len(close) >= 250 → R/S analysis → float H
            │
            ▼
        broadcast_scalar_over_series: H → constant Series
```

### Edge Cases

| Case | Behavior |
|------|----------|
| 249 bars | `None` → all-NaN column |
| 250 bars exactly | R/S analysis runs, valid H returned |
| `min_bars=50` explicit | Override honored (for callers who accept the risk) |
| `fractal_regime` with 249 bars | Returns `"unknown"` (H is None) |
| Empty DataFrame | Already handled: returns `None` immediately |
