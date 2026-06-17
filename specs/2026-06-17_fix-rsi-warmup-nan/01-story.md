# Fix RSI and Other Indicators Returning 0.0 Instead of NaN During Warmup

## User Story

As a **quantitative trader using RSI in strategy conditions**, I want RSI to show `NaN` (not `0.0`) when there aren't enough bars yet to compute a valid 14-period RSI, so that my strategies don't false-trigger on "oversold" signals during warmup.

## Context

During a comprehensive MCP audit (2026-06-17, ETH-USDC 1h), `rsi_14` returned `0.0` for early bars instead of `NaN`. An RSI of 0 means "extremely oversold" — but here it just meant "not enough data." This is misleading and can cause strategy conditions like `rsi < 30` to incorrectly fire during warmup.

### Root Cause

The issue is in the interaction between `pandas_ta` and `_safe_ta`:

1. `_safe_ta` wraps pandas_ta calls. When pandas_ta returns `None` (insufficient data), `_safe_ta` converts it to a NaN-filled Series. ✅
2. `ta.sma(close, length=20)` with < 20 bars → returns `None` → `_safe_ta` → NaN. ✅ Correct.
3. **`ta.rsi(close, length=14)` with < 14 bars → returns a partial Series with 0.0 values → `_safe_ta` passes it through.** ❌ Wrong.

The problem is that `pandas_ta`'s RSI implementation computes partial results (RSI=0 when all gains are zero due to a short downtrend) instead of returning `None`. `_safe_ta` only guards against `None`, not against partial results.

### Scope — Which indicators are affected?

Every `_safe_ta` caller passes `length=` as a keyword argument. The following indicators **could** be affected (if their pandas_ta function returns partial results instead of `None`):

| Handler | pandas_ta function | Returns None on short data? |
|---------|-------------------|:---:|
| `rsi_7`, `rsi_14` | `ta.rsi` | **No** — returns partial Series (0.0) |
| `sma_10–200` | `ta.sma` | ✅ Yes — returns None |
| `ema_12`, `ema_26` | `ta.ema` | ✅ Yes — returns None |
| `atr` | `ta.atr` | ✅ Yes — returns None |
| `vwap` | `ta.vwap` | ✅ Yes — returns None |
| `ker`, `kama` | `ta.er`, `ta.kama` | ✅ Yes — returns None |

Only `ta.rsi` is confirmed to return partial results. The fix is defensive — it protects against any pandas_ta function that might do the same.

### Fix

Add 3 lines to `_safe_ta` in `_handler_registry.py` to auto-mask the first N bars based on the `length=` kwarg that every caller already passes:

```python
lookback = kwargs.get("length")
if lookback is not None and isinstance(result, pd.Series) and len(result) > lookback:
    result = result.copy()
    result.iloc[:lookback] = np.nan
```

This is backwards-compatible: if `length` is not in kwargs (unlikely, but defensive), the mask is skipped. If a function returns None (current behavior for most), the existing NaN-fill branch handles it.

## Non-Goals

- **Not adding a "nice error message"** — the existing `failed_indicators` reporting works correctly for handlers that crash. This fix is for handlers that "succeed" but return misleading values.
- **Not changing individual handlers** — the fix is in the shared `_safe_ta` utility, so all 13 call sites benefit automatically.
- **Not changing `_compute_dynamic`** — dynamic dispatch goes through a different path but also passes `length=` to `_safe_ta`.
