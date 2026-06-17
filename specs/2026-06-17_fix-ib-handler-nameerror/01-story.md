# Fix IB Handler NameError — `_IB_BARS_MAP` Not Defined

## User Story

As a **quantitative trader using Auction Market Theory**, I want the Initial Balance indicators (`ib_high`, `ib_low`, `ib_range`, `ib_midpoint`) to compute correctly on intraday data, so that I can build strategies that trade breakouts from the opening range.

## Context

The four Initial Balance (IB) indicators — `ib_high`, `ib_low`, `ib_range`, `ib_midpoint` — are critical for Auction Market Theory strategies. They compute the high, low, range, and midpoint of the first N bars of each trading day, then broadcast those values to all bars within that day.

During a comprehensive MCP-based audit (2026-06-17, ETH-USDC 1h via Hyperliquid), all four IB indicators failed with:

```
NameError: name '_IB_BARS_MAP' is not defined
```

**Root cause:** The function `_get_ib_bars()` in `inside_bar.py` (line 63) references three module-level constants — `_IB_BARS_MAP`, `_IB_MINUTES_MAP`, `_DEFAULT_IB_BARS` — that are defined only in `trend_breakout.py` (line 153) and never imported into `inside_bar.py`. These constants are dead code in `trend_breakout.py` (they're not used anywhere in that module).

The fix is a one-line-per-constant addition to `inside_bar.py` before the `_get_ib_bars` function definition. Optionally, the dead copies in `trend_breakout.py` can be removed to eliminate confusion.

## Non-Goals

Things explicitly NOT being built in this iteration:
- **Refactoring IB computation** — the existing `_compute_true_ib` algorithm works correctly; only the constants are missing.
- **Changing the IB bar-count heuristic** — the interval-to-bars mapping (`1h→1`, `30min→2`, etc.) is correct.
- **Adding IB to daily data** — IB is intraday-only by definition; daily bars have no concept of "first hour."
- **Fixing other handler modules** — this is scoped to `inside_bar.py` only.
