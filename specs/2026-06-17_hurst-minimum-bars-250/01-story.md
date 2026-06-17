# Raise Hurst Exponent Minimum Bars to 250

## User Story

As a **quantitative trader using Hurst exponent for regime detection**, I want the estimator to return `None` (not a noisy estimate) when there isn't enough data to produce a statistically meaningful result, so that I don't make trading decisions based on unreliable H values.

## Context

The Hurst exponent via R/S analysis estimates long-term memory in a time series. The estimator converges slowly — its variance is inversely proportional to the number of (lag, R/S) pairs available for the log-log regression that determines H.

### Statistical Analysis of the Current Implementation

The current `min_bars=100` produces:

| Bars | Regression points | Largest chunk size | Statistical quality |
|-----:|------------------:|-------------------:|---------------------|
| 30 | 4 | 4 | ❌ **Useless** — 4-point regression has no statistical power |
| 50 | 9 | 4 | ❌ Very noisy, wide confidence intervals |
| **100** (current) | 22 | 4 | ⚠️ Marginal — R/S at largest lag computed from only 4 chunks |
| 180 | 42 | 4 | ⚠️ More points but still 4-bar chunks at large lags |
| **250** | 47 | 5 | ✅ Meets literature minimum |
| 500 | 47 | 10 | ✅ Good power |
| 1000 | 47 | 20 | ✅ Strong |

At 100 bars with `max_lag = min(50, 100//4) = 25`:
- Lag=25 splits 100 returns into only 4 chunks of 25
- The R/S statistic for that lag is the mean of just 4 observations → very high variance
- The log-log regression has 22 points, but the largest lags (most important for H estimation) are the noisiest

### Academic Consensus

| Source | Minimum |
|--------|---------|
| Weron (2002), "Estimating long-range dependence" | **250** |
| Peters (1994), "Fractal Market Analysis" | **256** |
| Couillard & Davison (2005) | **256** |
| Lo (1991), "Long-Term Memory in Stock Market Prices" | 800+ (rigorous) |

The consensus floor is **250 observations**. Below this, H estimates have confidence intervals too wide to distinguish trend-following (H > 0.55) from random walk (H ≈ 0.50).

### Practical Impact

- **Daily data:** Need ~1 year (250 trading days ≈ 1 calendar year)
- **1h intraday data:** Need ~10.5 days (250 hours)
- **5m intraday data:** Need ~21 hours (250 five-minute bars)

This is reasonable — if you have less than a year of daily data, you shouldn't be estimating long-term memory.

### What Changes

The function signature, default behavior, and catalog metadata all change from 100 → 250. The algorithm itself is unchanged — it was already correct, just too permissive.

## Non-Goals

Things explicitly NOT being built in this iteration:
- **Rolling Hurst** — a separate metric for regime-change detection over windows is future work.
- **Alternative H estimators** — DFA, periodogram, wavelet methods are out of scope.
- **Changing the algorithm** — only the minimum-bar threshold; the R/S implementation is correct.
- **Adding `hurst_exponent_rolling`** — separate feature.
