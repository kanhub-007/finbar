## Domain Model

### Existing Components

| Component | Location | Role |
|-----------|----------|------|
| `_IB_BARS_MAP`, `_DEFAULT_IB_BARS`, `_IB_MINUTES_MAP` | `trend_breakout.py` (lines 153–155) | Module-level constants mapping interval names to bar counts. **Dead code** — never referenced within `trend_breakout.py`. |
| `_get_ib_bars(df)` | `inside_bar.py` (lines 54–66) | Determines how many bars constitute the Initial Balance period based on index frequency. References the three constants. |
| `_compute_true_ib(df, ib_bars)` | `inside_bar.py` (lines 69–102) | Groups bars by date, takes first N bars per day, computes IB high/low/range/midpoint, broadcasts to all bars. Uses `ib_cache` sentinel in `df.attrs` to avoid recomputation. |
| `_ib_high/_ib_low/_ib_range/_ib_midpoint` | `inside_bar.py` (lines 30–52) | Four `@_register` handlers that call `_compute_true_ib(df, _get_ib_bars(df))`. |

### Root Cause

`inside_bar.py` imports nothing from `trend_breakout.py`. The three constants exist only in `trend_breakout.py`'s module scope. When `_get_ib_bars()` executes, Python looks up `_IB_BARS_MAP` in the local scope, then the enclosing function, then `inside_bar.py`'s module scope → not found → `NameError`.

### Fix

Add the three constants to `inside_bar.py` immediately before `_get_ib_bars()`. Optionally delete them from `trend_breakout.py` (dead code cleanup — Slice 2).

### No New Components

This is a one-line-per-constant addition. No new files, no API changes, no test changes needed (existing IB tests were testing a different code path or mocking the constants).
