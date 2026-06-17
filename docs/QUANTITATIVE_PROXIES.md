# Quantitative Trading Proxies & Market Microstructure

> Finbar implements 200+ indicators computable from OHLCV bars — from
> traditional technical analysis to academic market microstructure models.
> This document covers the quantitative proxy families: spread estimation,
> liquidity measurement, order flow reconstruction, volatility estimation,
> jump detection, resiliency, seasonality, and the daily-to-intraday proxy
> estimators that simulate intraday structure when tick data is unavailable.

---

## Table of Contents

1. [Daily → Intraday Structure Proxies](#1-daily--intraday-structure-proxies)
2. [Spread Estimators](#2-spread-estimators)
3. [Liquidity & Price Impact](#3-liquidity--price-impact)
4. [Order Flow Proxies](#4-order-flow-proxies)
5. [Informed Trading Proxies](#5-informed-trading-proxies)
6. [Volatility Estimators](#6-volatility-estimators)
7. [Jump & Gap Detection](#7-jump--gap-detection)
8. [Market Resiliency](#8-market-resiliency)
9. [Intraday Seasonality](#9-intraday-seasonality)
10. [Auction Market Theory (AMT)](#10-auction-market-theory-amt)
11. [Data Class Compatibility](#11-data-class-compatibility)
12. [See Also](#12-see-also)

---

## 1. Daily → Intraday Structure Proxies

When only daily OHLCV data is available, these industry-standard estimators
simulate intraday market structure metrics. The `proxy_` prefix distinguishes
them from real intraday calculations (which use the base indicator name).

On intraday data, always use the real indicator (`vwap`, `ibs`, `atr`, etc.)
instead of the proxy versions.

### VWAP Proxy (Typical Price)

| Column | Formula | Description |
|--------|---------|-------------|
| `proxy_vwap` | `(H + L + C) / 3` | Statistical mean of the day's range. >0.95 correlation with intraday VWAP on normal/trend days. |

VWAP is the session's "fair value" — volume-weighted average of every trade.
Without intraday volume distribution, Typical Price is the standard substitute.

### Initial Balance Proxies

| Column | Formula | Description |
|--------|---------|-------------|
| `proxy_ib_high` | `Open + 0.1 × ATR` | Simulated first-hour high |
| `proxy_ib_low` | `Open − 0.1 × ATR` | Simulated first-hour low |

In Auction Market Theory, the Initial Balance (first 60 minutes of trading)
defines the day's range. The 0.1×ATR buffer ensures signals only trigger on
significant breakouts from the opening price.

### Institutional Presence Proxies

| Column | Formula | Description |
|--------|---------|-------------|
| `proxy_ibs` | `(C − L) / (H − L)` | Internal Bar Strength — closing drive proxy. >0.8 suggests institutional buying into the close. |
| `proxy_atr` | ATR(N) | Average True Range as a general-purpose volatility proxy. |
| `proxy_expected_move` | `0.8 × ATR` | Implied-volatility expected daily move. 0.8×ATR approximates 1σ options-implied move. |

The `rvol` indicator (`Volume / SMA(Volume, 20)`) detects institutional
participation: RVOL > 1.5 is the standard proxy for dark-pool sweeps and
institutional activity.

### Batch Computation

Requesting any `proxy_` indicator triggers all proxy columns as a batch
computation. There is no performance penalty for requesting all of them.

```
compute_indicators("AAPL", "1d", [
    "proxy_vwap",    # VWAP substitute
    "atr",           # required for proxy_ib_* and proxy_expected_move
    "rvol",          # institutional participation
    "sma_50"
])
```

---

## 2. Spread Estimators

Bid-ask spread estimation from daily OHLCV data. These are the academic
standard for measuring transaction costs when tick-level quote data
(TAQ, Dukascopy) is unavailable. All are **proxy confidence** — they estimate
the spread, they don't measure it.

### Roll Estimator (1984)

| Column | Formula | Description |
|--------|---------|-------------|
| `roll_spread` | `2 × √(−Cov(ΔP_t, ΔP_{t−1}))` | Serial covariance of close-to-close price changes caused by bid-ask bounce. The original spread proxy. Set to 0 when covariance is positive (~30-40% of stocks). |

### Recommended Estimators

| Column | Source | Method |
|--------|--------|--------|
| `fong_holden_tran_spread` | FHT | **Recommended.** Simple OHLC-based closed-form estimator, always positive. |
| `roll_spread` | Roll (1984) | Close-to-close serial covariance. Works for stocks; returns 0 for crypto. |
| `effective_tick_spread` | Goyenko-Holden-Trzcinka | Tick-based: close-to-close price clustering around tick multiples. Requires ≥60 bars. |
| `lot_zero_return_spread` | Lesmond-Ogden-Trzcinka | Proportion of zero-return days as a liquidity proxy. Requires ≥60 bars. |

> **Note (2026-06-17):** `corwin_schultz_spread`, `abdi_ranaldo_spread`,
> and `chung_zhang_spread` were removed. These cross-sectional estimators
> return 0.0 for single-asset time series (the `alpha.clip(lower=0)` path
> is always taken in trending markets). Use `fong_holden_tran_spread` for
> OHLC-based estimates or `roll_spread` for close-based.

### When to use which

| Estimator | Best for | Limitation |
|-----------|----------|------------|
| `fong_holden_tran_spread` | **General purpose, any asset** | — |
| `roll_spread` | Stocks with bid-ask bounce | Breaks when covariance is positive (trending markets, crypto) |
| `effective_tick_spread` | Stocks with tick-size constraints | Requires tick-size knowledge, ≥60 bars |
| `lot_zero_return_spread` | Illiquid assets | Requires ≥60 bars |

```
compute_indicators("AAPL", "1d", [
    "fong_holden_tran_spread",
    "roll_spread"
])
```

---

## 3. Liquidity & Price Impact

How much does a trade move the market? These metrics measure the cost of
trading and the depth of the order book — from daily data.

### Illiquidity Measures

| Column | Source | Formula | Interpretation |
|--------|--------|---------|----------------|
| `amihud_illiq` | Amihud (2002) | \|return\| / dollar_volume | Higher = more illiquid. Standard academic liquidity measure. |
| `amivest_liquidity` | Amivest | dollar_volume / \|price_change\| | Inverse of Amihud. Higher = more liquid. |
| `liu_illiq` | Liu (2006) | Proportion of zero-volume days | Captures trading frequency dimension. |

### Price Impact

| Column | Source | Description |
|--------|--------|-------------|
| `florackis_lambda` | Florackis | Return-to-volume ratio liquidity measure. |
| `hasbrouck_daily_lambda` | Hasbrouck | Daily price impact: how much price moves per unit of volume. |
| `bao_pan_zhou_cost` | Bao-Pan-Zhou | Trading cost proxy from close-to-close return reversal (γ measure). |

### Strategy Use

- `amihud_illiq` rising → market becoming less liquid. Reduce position size.
- `hasbrouck_daily_lambda` spiking → trades have high impact. Use limit orders.
- `bao_pan_zhou_cost` near zero → low friction. Good for high-frequency strategies.

```
compute_indicators("TSLA", "1d", [
    "amihud_illiq",
    "hasbrouck_daily_lambda",
    "liu_illiq"
])
```

---

## 4. Order Flow Proxies

Reconstruct buy/sell volume classification and order flow imbalance from
OHLCV bars when actual trade-and-quote (TAQ) data is unavailable. Uses the
**Bulk Volume Classification (BVC)** method of Easley, Lopez de Prado, and
O'Hara.

### BVC — Volume Classification

| Column | Description |
|--------|-------------|
| `bvc_buy_volume` | Estimated buy volume: volume × probability of buy based on normalized price change |
| `bvc_sell_volume` | Estimated sell volume: volume × probability of sell |
| `bvc_ofi` | Order Flow Imbalance: `bvc_buy_volume − bvc_sell_volume` |

### Aggregated OFI

| Column | Description |
|--------|-------------|
| `signed_sqrt_volume_ofi` | Signed square-root volume OFI — dampens extreme values |
| `cumulative_signed_volume_ofi` | Running cumulative OFI — trend of buy/sell pressure |

### Volume Delta & Correlation

| Column | Description |
|--------|-------------|
| `cumulative_volume_delta` | Cumulative buy − sell delta. Rising CVD = net buying pressure. |
| `return_volume_correlation` | Rolling correlation between returns and volume. Positive = volume confirms direction. |

### Strategy Use

| Signal | Implication |
|--------|-------------|
| `bvc_ofi` strong positive + price up | Confirmed uptrend. Buy pullbacks. |
| `bvc_ofi` strong positive + price flat | Absorption — sellers absorbing. Prepare to short. |
| `cumulative_signed_volume_ofi` diverging from price | Hidden buying/selling. Potential reversal. |

```
compute_indicators("BTC", "1h", [
    "bvc_ofi",
    "cumulative_signed_volume_ofi",
    "bvc_buy_volume",
    "bvc_sell_volume"
])
```

---

## 5. Informed Trading Proxies

Probability that a trade originates from an informed participant (with
non-public or superior information). Estimated from price/volume dynamics.

| Column | Source | Description |
|--------|--------|-------------|
| `daily_vpin` | Easley et al. (2012) | Volume-synchronized probability of informed trading. High VPIN → high toxic order flow risk. |
| `spread_based_pin_proxy` | — | PIN proxy derived from bid-ask spread metrics. Higher PIN → wider spreads as market makers protect against adverse selection. |

### Strategy Use

- `daily_vpin` > 0.8: Market dominated by informed flow. Avoid fading.
- `daily_vpin` < 0.2: Noise trader environment. Mean reversion works well.
- Rising `spread_based_pin_proxy`: Adverse selection increasing. Widen stops.

---

## 6. Volatility Estimators

Annualized volatility from OHLCV data. Ordered from naive (close-to-close only)
to sophisticated (full OHLC + overnight gap). The Yang-Zhang estimator is the
most accurate daily-data volatility proxy available.

### OHLC-Based Estimators

| Column | Source | Data Used | Accuracy |
|--------|--------|-----------|----------|
| `close_to_close_vol` | Naive | Close only | Lowest — misses all intraday movement |
| `parkinson_vol` | Parkinson (1980) | High-Low range | ~5× more efficient than close-to-close |
| `garman_klass_vol` | Garman-Klass (1980) | O, H, L, C | ~7.4× more efficient than close-to-close |
| `rogers_satchell_vol` | Rogers-Satchell (1991) | O, H, L, C | Drift-independent — works in trending markets |
| `gk_plus_overnight_vol` | — | O, H, L, C + overnight | Garman-Klass extended with overnight gap |
| `yang_zhang_vol` | Yang-Zhang (2000) | O, H, L, C + overnight | **Most accurate daily proxy.** ~14× more efficient than close-to-close. |
| `meilijson_vol` | Meilijson | O, H, L, C | Alternative OHLC formulation |

### Intraday-Only Estimators

These require intraday bars (5min/30min/1h). Not computable on daily data.

| Column | Description |
|--------|-------------|
| `realized_vol_5m` | Realized volatility from 5-minute returns |
| `realized_vol_15m` | Realized volatility from 15-minute returns |
| `realized_vol_1h` | Realized volatility from 1-hour returns |
| `bipower_variation` | Jump-robust volatility (Barndorff-Nielsen & Shephard). Separates continuous from jump components. |

### Higher Moments

| Column | Description |
|--------|-------------|
| `daily_return_skewness` | Rolling skewness of daily returns. Negative = crash risk. |
| `daily_return_kurtosis` | Rolling kurtosis. High = fat tails, extreme events more likely. |
| `realized_skewness` | Skewness from intraday returns (intraday data only) |
| `realized_kurtosis` | Kurtosis from intraday returns (intraday data only) |

### Choosing an Estimator

| Scenario | Best estimator |
|----------|---------------|
| Daily data, trending market | `rogers_satchell_vol` |
| Daily data, best accuracy | `yang_zhang_vol` |
| Daily data, quick baseline | `parkinson_vol` |
| Intraday data, need jump-robust | `bipower_variation` |
| Intraday data, specific horizon | `realized_vol_5m` / `15m` / `1h` |

```
compute_indicators("AAPL", "1d", [
    "yang_zhang_vol",
    "garman_klass_vol",
    "daily_return_skewness",
    "daily_return_kurtosis"
])
```

---

## 7. Jump & Gap Detection

Identify discontinuous price moves — overnight gaps, intraday jumps, and
extreme returns. These matter because jumps violate the assumptions of
continuous-time models and represent unhedgeable risk.

### Daily-Data Proxies

| Column | Description |
|--------|-------------|
| `jump_gap_proxy` | Jump detection from overnight gap magnitude vs. typical range |
| `overnight_gap_proxy` | Raw overnight gap measure (close → next open) |
| `extreme_return_flag` | Binary: return exceeds N standard deviations of rolling distribution |
| `cc_rs_jump_proxy` | Close-to-close / range-based jump test |

### Intraday-Only

| Column | Description |
|--------|-------------|
| `lee_mykland_jump` | Lee-Mykland (2008): formal intraday jump test. Identifies specific bars where jumps occurred. Requires intraday data. |

### Strategy Use

- `extreme_return_flag` + `overnight_gap_proxy` high: Gap risk elevated. Reduce
  overnight exposure or tighten stops.
- `jump_gap_proxy` cluster: Regime change underway. Avoid mean reversion.
- `lee_mykland_jump` (intraday): Jump occurred on this specific bar. Caution
  entering — high risk of continuation or reversal.

```
compute_indicators("TSLA", "1d", [
    "overnight_gap_proxy",
    "extreme_return_flag",
    "jump_gap_proxy"
])
```

---

## 8. Market Resiliency

How quickly does the market return to equilibrium after absorbing a trade?
High resiliency = price impact dissipates quickly. Low resiliency = trades
leave lasting footprints.

| Column | Description |
|--------|-------------|
| `resiliency_autocorr` | Return autocorrelation as a resiliency measure. Negative autocorrelation (mean reversion) = high resiliency. |
| `resiliency_spread_to_impact` | Ratio of spread to price impact. Higher = more resilient (spread is large relative to lasting impact). |
| `inverse_amihud_resiliency` | Inverse of Amihud illiquidity. Higher = more resilient. |

### Strategy Use

- High `resiliency_autocorr` (negative): Market absorbs orders well. Use
  aggressive entries.
- Low `resiliency_spread_to_impact`: Trades have lasting impact. Use
  patient entries and wider stops.

```
compute_indicators("AAPL", "1d", [
    "resiliency_autocorr",
    "inverse_amihud_resiliency"
])
```

---

## 9. Intraday Seasonality

Volume and return patterns that repeat within the trading day: U-shaped
volume curves, overnight vs. intraday return decomposition, and opening/closing
volume concentration.

### Daily-Data Proxies

| Column | Description |
|--------|-------------|
| `overnight_return` | Close → next open return component |
| `intraday_return` | Open → close return component |
| `parametric_u_shape` | Parametric U-shaped intraday volume curve proxy |
| `first_last_hour_vol_fraction` | Fraction of volume occurring in first and last trading hours |

### Intraday-Only

| Column | Description |
|--------|-------------|
| `intraday_volume_curve` | Empirical volume curve from intraday bars |
| `empirical_volume_curve` | Empirical volume curve from 5-minute bars |

### Strategy Use

- `overnight_return` consistently positive + `intraday_return` flat: Most
  gains come from gaps. Trade the close → open, not intraday.
- `first_last_hour_vol_fraction` high: Liquidity concentrated at open/close.
  Execute entries near these periods.

```
compute_indicators("SPY", "1d", [
    "overnight_return",
    "intraday_return",
    "first_last_hour_vol_fraction"
])
```

---

## 10. Auction Market Theory (AMT)

Finbar implements the full Auction Market Theory framework from
Steidlmayer's CBOT methodology. This section provides a compact reference;
see [`TRADING_THEORIES.md`](TRADING_THEORIES.md) for strategy usage and
[`METRIC_CATALOG.md`](METRIC_CATALOG.md) for the complete indicator listing.

### VWAP Standard Deviation Bands

Session-scoped (reset daily). Intraday data only — on daily bars std = 0.

| Column | Description |
|--------|-------------|
| `vwap_session` | Session-scoped cumulative VWAP |
| `vwap_upper_1`, `vwap_lower_1` | VWAP ± 1σ |
| `vwap_upper_2`, `vwap_lower_2` | VWAP ± 2σ |

### Volume Profile (Parkinson-Weighted)

| Column | Description |
|--------|-------------|
| `vp_poc` | Point of Control — price with most volume |
| `vp_vah`, `vp_val` | Value Area High/Low — 68% volume zone boundaries |
| `vp_poc_Nd`, `vp_vah_Nd`, `vp_val_Nd` | Rolling N-session medians (e.g., `vp_poc_5d`, `vp_poc_20d`) |
| `cvp_poc_Nd`, `cvp_vah_Nd`, `cvp_val_Nd` | True composite (stacked) N-session profiles |
| `rvp_poc_N`, `rvp_vah_N`, `rvp_val_N` | Rolling N-bar profiles (e.g., `rvp_poc_48`, `rvp_poc_336` for crypto) |

### Market Profile (TPO)

| Column | Description |
|--------|-------------|
| `mp_poc`, `mp_vah`, `mp_val` | Time-at-Price POC/VAH/VAL. TPO counts instead of volume. |

### Auction State Classifiers

| Column | Type | Description |
|--------|------|-------------|
| `inside_value`, `above_value`, `below_value` | bool | Position relative to value area |
| `at_poc`, `near_vah`, `near_val` | bool | Proximity to key levels |
| `balance_status` | str | BALANCED / IMBALANCED_UP / IMBALANCED_DOWN |
| `profile_shape` | str | Dominant shape: normal / p_shape / b_shape / d_shape / neutral |
| `day_type_classification` | str | TREND_UP / TREND_DOWN / RANGE / NEUTRAL |
| `poc_slope_5`, `poc_slope_20` | float | POC trend slope over 5/20 sessions |

### AMT Rule Signals

| Column | Rule | Description |
|--------|------|-------------|
| `acceptance_into_value` | 1 | Price enters value from outside |
| `rejection_from_edge` | 2 | Price touches VAH/VAL and reverses |
| `acceptance_outside_value` | 3 | Price leaves value → seeks new fair value |
| `poc_rejection` | 4 | Strong reversal at POC |
| `edge_volume_building` | 5 | Volume building at value edge (breakout setup) |
| `value_area_migration` | — | POC trend: HIGHER / LOWER / STABLE |

### Data Quality Notes

- **Best results:** 30min/1h intraday data. Multi-bar sessions produce
  meaningful volume distributions.
- **Daily data:** Each bar = one session. POC ≈ typical price, VAH ≈ high,
  VAL ≈ low. Use rolling composites (`vp_poc_5d`, `vp_poc_20d`) or bar-window
  variants (`rvp_poc_N`) for multi-day analysis.
- **Accuracy:** OHLCV-based approximations. POC: ±1-2% of actual tick-level
  POC. VAH/VAL: ±3-5%.

### Usage

```
compute_indicators("AAPL", "30min", [
    "vwap_session", "vwap_upper_1", "vwap_lower_1",
    "vp_poc", "vp_vah", "vp_val",
    "vp_poc_5d", "vp_vah_5d", "vp_val_5d",
    "mp_poc", "mp_vah", "mp_val",
    "inside_value", "balance_status", "profile_shape",
    "acceptance_outside_value", "rejection_from_edge",
    "poc_slope_20"
])
```

---

## 11. Data Class Compatibility

Which proxy families can you compute from which data?

| Family | Daily (1d/1w) | Intraday (5m/30m/1h) | Best accuracy |
|--------|:---:|:---:|---|
| Structure Proxies (`proxy_*`) | ✅ | N/A (use real indicators) | Daily only |
| Spread Estimators | ✅ ⚠️ | ✅ | Intraday |
| Liquidity & Impact | ✅ | ✅ | Daily |
| Order Flow (BVC) | ✅ ⚠️ | ✅ | Intraday |
| Informed Trading | ✅ ⚠️ | ✅ | Intraday |
| Volatility — daily estimators | ✅ | ✅ | Intraday |
| Volatility — realized/bipower | ❌ | ✅ | Intraday |
| Jump — daily proxies | ✅ | ✅ | Intraday |
| Jump — Lee-Mykland | ❌ | ✅ | Intraday |
| Resiliency | ✅ | ✅ | Daily |
| Seasonality — daily proxies | ✅ ⚠️ | ✅ | Intraday |
| Seasonality — empirical curves | ❌ | ✅ | Intraday |
| AMT — Volume Profile | ✅ ⚠️ | ✅ | Intraday |
| AMT — VWAP Session | ❌ | ✅ | Intraday |
| AMT — State & Rules | ✅ | ✅ | Either |
| Derivatives (CoinGlass) | 🔑 | 🔑 | External |

**Key:**
- ✅ Fully computable
- ⚠️ Computable but proxy confidence (OHLCV approximation, not tick-level truth)
- ❌ Not computable without intraday data
- 🔑 External data fetch required (`fetch_derivatives`)

---

## 12. See Also

- **[`METRIC_CATALOG.md`](METRIC_CATALOG.md)** — Complete reference of all
  219 indicators organized by family with data class compatibility.
- **[`TRADING_THEORIES.md`](TRADING_THEORIES.md)** — Strategy usage guide
  with JSON examples for Wyckoff, SMC, Supply/Demand, Fibonacci, Chaos
  Theory, and AMT.
- **[`BACKTESTING.md`](BACKTESTING.md)** — How to run backtests with these
  indicators.
- **[C:/HAL/docs/Intraday_Proxies_vs_Actual_Methods.md](../C:/HAL/docs/Intraday_Proxies_vs_Actual_Methods.md)**
  — In-depth academic reference on every proxy method, accuracy comparisons,
  and when each proxy breaks down.
