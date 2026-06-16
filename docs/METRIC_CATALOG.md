# Metric & Indicator Catalog

> Complete reference of all ~200+ computable indicators, metrics, and signals
> in Finbar. Organized by trading theory and measurement family. Every entry
> notes computability by data class (daily OHLCV vs. intraday OHLCV).

---

## Table of Contents

1. [Traditional Technical Analysis](#1-traditional-technical-analysis)
2. [Auction Market Theory (AMT)](#2-auction-market-theory-amt)
3. [Wyckoff / Volume Spread Analysis (VSA)](#3-wyckoff--volume-spread-analysis-vsa)
4. [Smart Money Concepts (SMC / ICT)](#4-smart-money-concepts-smc--ict)
5. [Supply & Demand Zones](#5-supply--demand-zones)
6. [Fibonacci Tools](#6-fibonacci-tools)
7. [Bill Williams / Chaos Theory](#7-bill-williams--chaos-theory)
8. [Market Microstructure — Spread Estimators](#8-market-microstructure--spread-estimators)
9. [Market Microstructure — Liquidity & Impact](#9-market-microstructure--liquidity--impact)
10. [Order Flow Proxies](#10-order-flow-proxies)
11. [Informed Trading Proxies](#11-informed-trading-proxies)
12. [Volatility Estimators](#12-volatility-estimators)
13. [Jump & Gap Detection](#13-jump--gap-detection)
14. [Market Resiliency](#14-market-resiliency)
15. [Intraday Seasonality](#15-intraday-seasonality)
16. [Pattern & Trend Structure](#16-pattern--trend-structure)
17. [Market Regime Detection](#17-market-regime-detection)
18. [Derivatives Data (CoinGlass)](#18-derivatives-data-coinglass)
19. [Quantitative Proxies (Daily → Intraday)](#19-quantitative-proxies-daily--intraday)
20. [Volume & Trade Count](#20-volume--trade-count)
21. [Data Class Compatibility Matrix](#21-data-class-compatibility-matrix)

---

## Legend

| Computability | Symbol | Meaning |
|---|---|---|
| ✅ | Computable | Works on this data class |
| ❌ | Unavailable | Not computable — needs richer data |
| ⚠️ | Proxy-only | Computes but uses a proxy estimator |
| 🔑 | External | Requires CoinGlass/external data fetch |

---

## 1. Traditional Technical Analysis

Core indicators usable as building blocks in any strategy.

| Indicator | Type | Daily | Intraday | Description |
|-----------|------|-------|----------|-------------|
| `sma_N` | Trend | ✅ | ✅ | Simple moving average (period N=2–500) |
| `ema_N` | Trend | ✅ | ✅ | Exponential moving average |
| `rsi_N` | Momentum | ✅ | ✅ | Relative Strength Index (period N=2–100) |
| `macd` | Momentum | ✅ | ✅ | MACD line (12/26 EMA difference) |
| `macd_signal` | Momentum | ✅ | ✅ | MACD signal line (9-period EMA of MACD) |
| `macd_hist` | Momentum | ✅ | ✅ | MACD histogram (MACD − signal) |
| `atr` | Volatility | ✅ | ✅ | Average True Range (period 2–200) |
| `adx` | Trend strength | ✅ | ✅ | Average Directional Index (period 2–100) |
| `bb_upper` | Envelope | ✅ | ✅ | Bollinger upper band (period 2–200) |
| `bb_middle` | Envelope | ✅ | ✅ | Bollinger middle band (SMA) |
| `bb_lower` | Envelope | ✅ | ✅ | Bollinger lower band |
| `vwap` | Price | ✅ | ✅ | Volume-Weighted Average Price (continuous) |
| `ibs` | Sentiment | ✅ | ✅ | Internal Bar Strength: `(C−L)/(H−L)` |
| `rvol` | Volume | ✅ | ✅ | Relative Volume: `Volume / SMA(Volume, 20)` |
| `ker` | Efficiency | ✅ | ✅ | Kauffman Efficiency Ratio |
| `kama` | Trend | ✅ | ✅ | Kauffman Adaptive Moving Average |
| `price_vs_sma20` | Position | ✅ | ✅ | Price relative to 20-period SMA |
| `trend_direction` | Trend | ✅ | ✅ | Trend direction (+1 up, −1 down, 0 flat) |
| `trend_strength` | Trend | ✅ | ✅ | Trend strength score (0–100) |
| `trend_status` | Trend | ✅ | ✅ | Trend status (STRONG_UP, WEAK_UP, etc.) |
| `swing_high_20` | Structure | ✅ | ✅ | 20-bar swing high |
| `swing_low_20` | Structure | ✅ | ✅ | 20-bar swing low |
| `breakout_level` | Structure | ✅ | ✅ | Nearest breakout price level |
| `breakout_signal` | Structure | ✅ | ✅ | Breakout signal (+1 / −1 / 0) |
| `is_power_zone` | Structure | ✅ | ✅ | Price in power zone (trend-aligned level) |
| `breakout_quality` | Structure | ✅ | ✅ | Breakout quality score |
| `vol_buffer_high` | Volume | ✅ | ✅ | Volume-based buffer above price |
| `vol_buffer_low` | Volume | ✅ | ✅ | Volume-based buffer below price |
| `ib_high` | Session | ❌ | ✅ | Initial Balance high (first-hour range). Intraday only — needs session-scoped first-hour bars |
| `ib_low` | Session | ❌ | ✅ | Initial Balance low. Intraday only — needs session-scoped first-hour bars |
| `ib_midpoint` | Session | ❌ | ✅ | Initial Balance midpoint. Intraday only — needs session-scoped first-hour bars |
| `ib_range` | Session | ❌ | ✅ | Initial Balance range width. Intraday only — needs session-scoped first-hour bars |
| `coil_intensity` | Structure | ✅ | ✅ | Coil/compression intensity score |
| `is_coiled` | Structure | ✅ | ✅ | Binary: market is in a coil/compression |

---

## 2. Auction Market Theory (AMT)

Based on Steidlmayer's CBOT framework. Best on intraday data (30min/1h);
use rolling composites on daily.

### VWAP Standard Deviation Bands

Session-scoped VWAP with 1σ and 2σ bands. Unlike the continuous `vwap`
(pandas_ta), these reset each calendar day.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `vwap_session` | ❌ | ✅ | Session-scoped cumulative VWAP (resets daily) |
| `vwap_upper_1` | ❌ | ✅ | VWAP + 1σ |
| `vwap_lower_1` | ❌ | ✅ | VWAP − 1σ |
| `vwap_upper_2` | ❌ | ✅ | VWAP + 2σ |
| `vwap_lower_2` | ❌ | ✅ | VWAP − 2σ |

### Volume Profile

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `vp_poc` | ✅ | ✅ | Point of Control — price with most volume |
| `vp_vah` | ✅ | ✅ | Value Area High — 68% volume zone top |
| `vp_val` | ✅ | ✅ | Value Area Low — 68% volume zone bottom |
| `vp_poc_Nd` | ✅ | ✅ | Rolling N-session POC median (e.g. `vp_poc_5d`, `vp_poc_20d`) |
| `vp_vah_Nd` | ✅ | ✅ | Rolling N-session VAH median |
| `vp_val_Nd` | ✅ | ✅ | Rolling N-session VAL median |
| `cvp_poc_Nd` | ✅ | ✅ | True composite (stacked) N-session POC |
| `cvp_vah_Nd` | ✅ | ✅ | Composite N-session VAH |
| `cvp_val_Nd` | ✅ | ✅ | Composite N-session VAL |
| `rvp_poc_N` | ✅ | ✅ | Rolling N-bar POC (e.g. `rvp_poc_48`, `rvp_poc_336`) |
| `rvp_vah_N` | ✅ | ✅ | Rolling N-bar VAH |
| `rvp_val_N` | ✅ | ✅ | Rolling N-bar VAL |

> **Daily data note:** Each bar = one session. POC ≈ typical price, VAH ≈ high,
> VAL ≈ low. Use rolling composites (`vp_poc_5d`, `vp_poc_20d`) or bar-window
> variants (`rvp_poc_N`) for meaningful multi-day value areas.

### Market Profile (TPO)

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `mp_poc` | ✅ | ✅ | Point of Control — price with most TPOs (time) |
| `mp_vah` | ✅ | ✅ | Value Area High — 68% TPO zone top |
| `mp_val` | ✅ | ✅ | Value Area Low — 68% TPO zone bottom |

### Auction State Classifiers

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `inside_value` | ✅ | ✅ | Close between VAL and VAH |
| `above_value` | ✅ | ✅ | Close above VAH |
| `below_value` | ✅ | ✅ | Close below VAL |
| `at_poc` | ✅ | ✅ | Close within 2% of value area width from POC |
| `near_vah` | ✅ | ✅ | Close within 10% of VAH |
| `near_val` | ✅ | ✅ | Close within 10% of VAL |
| `balance_status` | ✅ | ✅ | BALANCED / IMBALANCED_UP / IMBALANCED_DOWN |
| `distance_to_vah_pct` | ✅ | ✅ | Percentage distance to VAH |
| `distance_to_val_pct` | ✅ | ✅ | Percentage distance to VAL |
| `value_area_width_pct` | ✅ | ✅ | Value area width as percentage |

### AMT Rule Signals

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `acceptance_into_value` | ✅ | ✅ | Rule 1: Price enters value from outside |
| `rejection_from_edge` | ✅ | ✅ | Rule 2: Price touches VAH/VAL and reverses |
| `acceptance_outside_value` | ✅ | ✅ | Rule 3: Price leaves value → seeks new fair value |
| `poc_rejection` | ✅ | ✅ | Rule 4: Strong reversal at POC |
| `edge_volume_building` | ✅ | ✅ | Rule 5: Volume accumulating at edge |
| `value_area_migration` | ✅ | ✅ | POC trend: HIGHER / LOWER / STABLE |

### Profile Shape Analysis

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `profile_shape` | ✅ | ✅ | Dominant profile shape classifier |
| `is_normal_shape` | ✅ | ✅ | Bell-shaped (balanced) profile |
| `is_p_shape` | ✅ | ✅ | P-shape (heavy top, bullish) |
| `is_b_shape` | ✅ | ✅ | b-shape (heavy bottom, bearish) |
| `is_d_shape` | ✅ | ✅ | D-shape (heavy middle, extreme balance) |
| `is_neutral_shape` | ✅ | ✅ | Thin/elongated (trend day) |
| `day_type_classification` | ✅ | ✅ | Day type: trend_up / trend_down / range / neutral |
| `poc_slope_5` | ✅ | ✅ | POC trend slope over 5 sessions |
| `poc_slope_20` | ✅ | ✅ | POC trend slope over 20 sessions |

---

## 3. Wyckoff / Volume Spread Analysis (VSA)

Richard Wyckoff's methodology analyzing price action, volume, and the
relationship between them to identify institutional accumulation and
distribution.

### Wyckoff Phases

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `wyckoff_phase` | ✅ | ✅ | Current Wyckoff phase (ACCUMULATION / MARKUP / DISTRIBUTION / MARKDOWN / NEUTRAL) |
| `is_accumulation` | ✅ | ✅ | Binary: accumulation phase detected |
| `is_distribution` | ✅ | ✅ | Binary: distribution phase detected |
| `is_markup` | ✅ | ✅ | Binary: markup phase (uptrend) |
| `is_markdown` | ✅ | ✅ | Binary: markdown phase (downtrend) |
| `is_wyckoff_neutral` | ✅ | ✅ | Binary: neutral/transitional phase |

### VSA Signals

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `stopping_volume` | ✅ | ✅ | High volume halting a decline — potential accumulation |
| `climax_volume` | ✅ | ✅ | Ultra-high volume at market extreme — buying/selling climax |
| `no_demand` | ✅ | ✅ | Declining volume on an up bar — weak rally |
| `no_supply` | ✅ | ✅ | Declining volume on a down bar — weak selling |
| `effort_to_rise` | ✅ | ✅ | High volume + wide up range — genuine buying effort |
| `effort_to_fall` | ✅ | ✅ | High volume + wide down range — genuine selling effort |
| `effort_result_divergence` | ✅ | ✅ | High volume + small range — absorption, potential reversal |
| `bag_holding` | ✅ | ✅ | Long upper shadow on high volume — trapped longs |
| `shakeout` | ✅ | ✅ | Sudden drop + recovery on high volume — spring/UT |
| `vsa_test_signal` | ✅ | ✅ | Low-volume probe of support — successful test |
| `volume_trend_confirmation` | ✅ | ✅ | Volume direction aligned with price trend |
| `trend_phase` | ✅ | ✅ | Wyckoff trend phase classification |

---

## 4. Smart Money Concepts (SMC / ICT)

Internal Range Liquidity (IRL) / External Range Liquidity (ERL) framework
for institutional order flow interpretation.

### Structure

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `bos` | ✅ | ✅ | Break of Structure — trend continuation |
| `choch` | ✅ | ✅ | Change of Character — potential trend reversal |

### Liquidity Sweeps

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `liquidity_sweep_high` | ✅ | ✅ | Sweep above recent swing high (buyside liquidity taken) |
| `liquidity_sweep_low` | ✅ | ✅ | Sweep below recent swing low (sellside liquidity taken) |

### Order Blocks

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `bullish_order_block` | ✅ | ✅ | Last down candle before an uptrend (demand OB) |
| `bearish_order_block` | ✅ | ✅ | Last up candle before a downtrend (supply OB) |
| `breaker_block_bullish` | ✅ | ✅ | Failed bearish OB reclaimed as support |
| `breaker_block_bearish` | ✅ | ✅ | Failed bullish OB reclaimed as resistance |

### Fair Value Gaps

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `bullish_fvg` | ✅ | ✅ | Bullish imbalance zone (gap between wicks) |
| `bearish_fvg` | ✅ | ✅ | Bearish imbalance zone |

### Zone Classification

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `premium_discount_zone` | ✅ | ✅ | Premium / Equilibrium / Discount classification |

---

## 5. Supply & Demand Zones

Price levels where institutional buying (demand) or selling (supply) created
significant reversals.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `demand_zone_high` | ✅ | ✅ | Upper boundary of the nearest demand zone |
| `demand_zone_low` | ✅ | ✅ | Lower boundary of the nearest demand zone |
| `demand_zone_score` | ✅ | ✅ | Demand zone quality (freshness, strength, reaction) |
| `supply_zone_high` | ✅ | ✅ | Upper boundary of the nearest supply zone |
| `supply_zone_low` | ✅ | ✅ | Lower boundary of the nearest supply zone |
| `supply_zone_score` | ✅ | ✅ | Supply zone quality |
| `zone_signal` | ✅ | ✅ | Combined zone interaction signal |
| `zone_failure_bullish` | ✅ | ✅ | Supply zone broken to the upside |
| `zone_failure_bearish` | ✅ | ✅ | Demand zone broken to the downside |

---

## 6. Fibonacci Tools

Retracement and extension levels from recent swing highs and lows.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `fib_382_retrace` | ✅ | ✅ | 38.2% retracement of last major swing |
| `fib_500_retrace` | ✅ | ✅ | 50% retracement |
| `fib_618_retrace` | ✅ | ✅ | 61.8% retracement (golden ratio) |
| `fib_1618_extension` | ✅ | ✅ | 161.8% extension beyond the swing |
| `fib_confluence_score` | ✅ | ✅ | Confluence score across multiple Fibonacci levels |

---

## 7. Bill Williams / Chaos Theory

Williams' trading system based on fractal geometry and market psychology.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `awesome_oscillator` | ✅ | ✅ | AO: 5-period vs 34-period SMA of midpoints |
| `accelerator_oscillator` | ✅ | ✅ | AC: AO minus its 5-period SMA |
| `alligator_jaw` | ✅ | ✅ | Blue line (13-period SMMA, shifted 8) |
| `alligator_teeth` | ✅ | ✅ | Red line (8-period SMMA, shifted 5) |
| `alligator_lips` | ✅ | ✅ | Green line (5-period SMMA, shifted 3) |
| `alligator_status` | ✅ | ✅ | Sleeping / Awakening / Eating phase |
| `williams_fractal_high` | ✅ | ✅ | Up fractal (5-bar swing high pattern) |
| `williams_fractal_low` | ✅ | ✅ | Down fractal (5-bar swing low pattern) |

### Fractal Market Hypothesis

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `hurst_exponent` | ✅ | ✅ | H<0.5 = mean-reverting, H=0.5 = random, H>0.5 = trending. Requires ≥100 bars; returns None otherwise |
| `fractal_regime` | ✅ | ✅ | Fractal-based market regime classification |

---

## 8. Market Microstructure — Spread Estimators

Bid-ask spread estimation from daily OHLCV data when tick data is unavailable.
All are ⚠️ proxy confidence.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `roll_spread` | ✅ | ✅ | Roll (1984): serial covariance of close-to-close price changes |
| `corwin_schultz_spread` | ✅ | ✅ | Corwin-Schultz (2012): OHLC-based, overnight-gap-adjusted. Gold standard daily proxy |
| `abdi_ranaldo_spread` | ✅ | ✅ | Abdi-Ranaldo (2017): mid-price + close covariance |
| `chung_zhang_spread` | ✅ | ✅ | Chung-Zhang: simplified OHLC-based estimator |
| `effective_tick_spread` | ✅ | ✅ | Tick-based: close-to-close price clustering. Requires ≥60 bars for lookback window |
| `fong_holden_tran_spread` | ✅ | ✅ | FHT: simple OHLC-based estimator |
| `lot_zero_return_spread` | ✅ | ✅ | LOT: zero-return proportion method. Requires ≥60 bars for lookback window |

---

## 9. Market Microstructure — Liquidity & Impact

Measures of market depth, price impact, and trading costs.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `amihud_illiq` | ✅ | ✅ | Amihud (2002): \|return\| / dollar_volume |
| `amivest_liquidity` | ✅ | ✅ | Inverse Amihud: dollar volume per unit price change |
| `liu_illiq` | ✅ | ✅ | Liu (2006): proportion of zero-volume days |
| `florackis_lambda` | ✅ | ✅ | Florackis: return-to-volume ratio |
| `hasbrouck_daily_lambda` | ✅ | ✅ | Hasbrouck: daily price impact from close-to-close |
| `bao_pan_zhou_cost` | ✅ | ✅ | Bao-Pan-Zhou: trading cost from close-to-close reversal |

---

## 10. Order Flow Proxies

Buy/sell volume classification and order flow imbalance from OHLCV bars.
All are ⚠️ proxy confidence.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `bvc_buy_volume` | ✅ | ✅ | Bulk Volume Classification: estimated buy volume |
| `bvc_sell_volume` | ✅ | ✅ | BVC: estimated sell volume |
| `bvc_ofi` | ✅ | ✅ | BVC order flow imbalance: buy − sell volume |
| `cumulative_signed_volume_ofi` | ✅ | ✅ | Cumulative signed volume OFI from BVC |
| `signed_sqrt_volume_ofi` | ✅ | ✅ | Signed square-root volume OFI |
| `cumulative_volume_delta` | ✅ | ✅ | CVD: cumulative buy − sell delta |
| `return_volume_correlation` | ✅ | ✅ | Rolling correlation between returns and volume |

---

## 11. Informed Trading Proxies

Probability of informed trading estimates from price/volume dynamics.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `daily_vpin` | ✅ | ✅ | Volume-synchronized probability of informed trading |
| `spread_based_pin_proxy` | ✅ | ✅ | PIN proxy from bid-ask spread metrics |

---

## 12. Volatility Estimators

Annualized volatility estimators. Ordered from naive to most sophisticated.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `close_to_close_vol` | ✅ | ✅ | Naive: close-to-close return standard deviation |
| `parkinson_vol` | ✅ | ✅ | Parkinson (1980): high-low range estimator |
| `garman_klass_vol` | ✅ | ✅ | Garman-Klass (1980): OHLC estimator |
| `gk_plus_overnight_vol` | ✅ | ✅ | Garman-Klass extended with overnight gap component |
| `rogers_satchell_vol` | ✅ | ✅ | Rogers-Satchell (1991): drift-independent OHLC estimator |
| `yang_zhang_vol` | ✅ | ✅ | Yang-Zhang (2000): OHLC + overnight gap. Most accurate daily proxy |
| `meilijson_vol` | ✅ | ✅ | Meilijson: alternative OHLC estimator |
| `bipower_variation` | ❌ | ✅ | Jump-robust volatility from intraday returns |
| `realized_vol_5m` | ❌ | ✅ | Realized volatility from 5-minute returns |
| `realized_vol_15m` | ❌ | ✅ | Realized volatility from 15-minute returns |
| `realized_vol_1h` | ❌ | ✅ | Realized volatility from 1-hour returns |

### Higher Moments

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `daily_return_skewness` | ✅ | ✅ | Rolling skewness of daily returns |
| `daily_return_kurtosis` | ✅ | ✅ | Rolling kurtosis of daily returns |
| `realized_skewness` | ❌ | ✅ | Skewness from intraday returns |
| `realized_kurtosis` | ❌ | ✅ | Kurtosis from intraday returns |

---

## 13. Jump & Gap Detection

Identifying discontinuous price moves.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `jump_gap_proxy` | ✅ | ✅ | Jump detection from overnight gap in OHLC bars |
| `overnight_gap_proxy` | ✅ | ✅ | Overnight gap magnitude as jump indicator |
| `extreme_return_flag` | ✅ | ✅ | Binary flag for extreme returns exceeding threshold |
| `cc_rs_jump_proxy` | ✅ | ✅ | Close-to-close / range-based jump detection |
| `lee_mykland_jump` | ❌ | ✅ | Lee-Mykland (2008): intraday jump detection |

---

## 14. Market Resiliency

How quickly markets return to equilibrium after absorbing shocks.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `resiliency_autocorr` | ✅ | ✅ | Return autocorrelation as resiliency measure |
| `resiliency_spread_to_impact` | ✅ | ✅ | Spread-to-price-impact ratio |
| `inverse_amihud_resiliency` | ✅ | ✅ | Inverse Amihud illiquidity as resiliency proxy |

---

## 15. Intraday Seasonality

Volume and return patterns within the trading day.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `overnight_return` | ✅ | ✅ | Overnight return component from OHLC decomposition |
| `intraday_return` | ✅ | ✅ | Intraday return component from OHLC decomposition |
| `parametric_u_shape` | ✅ | ✅ | Parametric U-shaped intraday volume curve |
| `first_last_hour_vol_fraction` | ✅ | ✅ | Fraction of volume in first and last hours |
| `intraday_volume_curve` | ❌ | ✅ | Empirical volume curve from intraday bars |
| `empirical_volume_curve` | ❌ | ✅ | Empirical volume curve from 5-minute bars |

---

## 16. Pattern & Trend Structure

Chart pattern recognition and trend structure classification.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `hh_hl_pattern` | ✅ | ✅ | Higher-highs higher-lows (bullish trend structure) |
| `lh_ll_pattern` | ✅ | ✅ | Lower-highs lower-lows (bearish trend structure) |
| `swing_high_n` | ✅ | ✅ | N-bar swing high (parameterized window) |
| `swing_low_n` | ✅ | ✅ | N-bar swing low (parameterized window) |

---

## 17. Market Regime Detection

Multi-framework regime classification for strategy selection.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `market_regime` | ✅ | ✅ | Regime: TRENDING / RANGING / VOLATILE. Requires ≥220 bars for classification |
| `fractal_regime` | ✅ | ✅ | Fractal-based regime from Hurst exponent |
| `day_type_classification` | ✅ | ✅ | Day type: TREND_UP / TREND_DOWN / RANGE / NEUTRAL |

---

## 18. Derivatives Data (CoinGlass)

Crypto-specific derivatives market metrics. Requires `COINGLASS_API_KEY` and
prior `fetch_derivatives` call. 🔑 External data source.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `funding_rate` | 🔑 | 🔑 | Perpetual swap funding rate |
| `funding_rate_annualised` | 🔑 | 🔑 | Annualised funding rate |
| `open_interest` | 🔑 | 🔑 | Aggregate open interest |
| `open_interest_delta_1h` | 🔑 | 🔑 | 1-hour change in open interest |
| `open_interest_delta_24h` | 🔑 | 🔑 | 24-hour change in open interest |
| `cumulative_volume_delta` | 🔑 | 🔑 | CVD: cumulative buy − sell delta |
| `long_short_ratio` | 🔑 | 🔑 | Long/short account ratio |
| `liquidations_long_1h` | 🔑 | 🔑 | Long liquidations (1 hour) |
| `liquidations_short_1h` | 🔑 | 🔑 | Short liquidations (1 hour) |
| `liquidations_long_24h` | 🔑 | 🔑 | Long liquidations (24 hours) |
| `liquidations_short_24h` | 🔑 | 🔑 | Short liquidations (24 hours) |

---

## 19. Quantitative Proxies (Daily → Intraday)

Industry-standard estimators that simulate intraday structure from daily OHLCV
bars when tick/intraday data is unavailable. All are ⚠️ proxy confidence.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `proxy_vwap` | ✅ | N/A | Typical Price `(H+L+C)/3` as VWAP substitute |
| `proxy_ibs` | ✅ | N/A | Daily IBS as intraday closing drive proxy |
| `proxy_atr` | ✅ | N/A | ATR as volatility proxy |
| `proxy_garman_klass` | ✅ | N/A | Garman-Klass volatility from daily bars |
| `proxy_parkinson` | ✅ | N/A | Parkinson high-low volatility |
| `proxy_rogers_satchell` | ✅ | N/A | Rogers-Satchell volatility |
| `proxy_expected_move` | ✅ | N/A | 0.8 × ATR as implied-volatility expected move |
| `proxy_ib_high` | ✅ | N/A | Open + 0.1×ATR as Initial Balance high proxy |
| `proxy_ib_low` | ✅ | N/A | Open − 0.1×ATR as Initial Balance low proxy |

> **Note:** On intraday data, use the real indicators (`vwap`, `ibs`, `atr`,
> `parkinson_vol`, etc.) directly. Proxies exist only for daily-data backtests
> where the actual intraday metric is unavailable.

---

## 20. Volume & Trade Count

Volume distribution and trade frequency metrics.

> **Limitation:** `volume_to_trade_count_proxy` uses a hardcoded average trade
> size of 500 (`volume ÷ 500`) — a rough estimate only. No real trade count
> data is available from yfinance or Hyperliquid APIs.

| Indicator | Daily | Intraday | Description |
|-----------|-------|----------|-------------|
| `volume_to_trade_count_proxy` | ⚠️ | ⚠️ | Crude proxy: `volume ÷ 500`. No real trade count data used. |

---

## 21. Data Class Compatibility Matrix

Quick reference for which metric families require which data.

| Family | Daily (1d/1w) | Intraday (5m/30m/1h) | External Source |
|--------|:---:|:---:|:---:|
| Traditional TA | ✅ | ✅ | — |
| AMT — Volume Profile | ✅ ⚠️ | ✅ | — |
| AMT — VWAP Session | ❌ | ✅ | — |
| AMT — Market Profile | ✅ ⚠️ | ✅ | — |
| AMT — State & Rules | ✅ | ✅ | — |
| Wyckoff / VSA | ✅ | ✅ | — |
| SMC / ICT | ✅ | ✅ | — |
| Supply & Demand | ✅ | ✅ | — |
| Fibonacci | ✅ | ✅ | — |
| Bill Williams | ✅ | ✅ | — |
| Spread Estimators | ✅ ⚠️ | ✅ | — |
| Liquidity & Impact | ✅ | ✅ | — |
| Order Flow Proxies | ✅ ⚠️ | ✅ | — |
| Informed Trading | ✅ ⚠️ | ✅ | — |
| Volatility — daily estimators | ✅ | ✅ | — |
| Volatility — realized/bipower | ❌ | ✅ | — |
| Jump Detection — daily | ✅ | ✅ | — |
| Jump Detection — intraday | ❌ | ✅ | — |
| Resiliency | ✅ | ✅ | — |
| Intraday Seasonality — daily | ✅ ⚠️ | ✅ | — |
| Intraday Seasonality — empirical | ❌ | ✅ | — |
| Pattern & Structure | ✅ | ✅ | — |
| Regime Detection | ✅ | ✅ | — |
| Derivatives (CoinGlass) | 🔑 | 🔑 | CoinGlass |
| Volume & Trade Count | ⚠️ | ⚠️ | — |
| Quantitative Proxies | ✅ | N/A | — |

**Key:**
- ✅ Fully computable
- ⚠️ Computable but lower accuracy (OHLCV proxy vs. tick-level truth)
- ❌ Not computable — needs richer data
- 🔑 External data fetch required
- N/A Not applicable (use real indicator instead)

---

## Usage Patterns

### Fetching data + computing indicators

```python
# 1. Fetch prices
fetch_price_history("AAPL", "1h", start_date="2026-04-01")

# 2. Compute indicators server-side
compute_indicators("AAPL", "yfinance", "1h",
  indicators_json='["sma_50","rsi_14","atr","wyckoff_phase",'
                  '"bullish_order_block","liquidity_sweep_low",'
                  '"vp_poc","vp_vah","vp_val","balance_status"]',
  start_date="2026-04-01")

# 3. Backtest with artifact
backtest_strategy_definition(definition_json, bars_artifact_id=job_id, ...)
```

### Strategy JSON — referencing indicators

```json
{
  "entry": {
    "condition": {
      "operator": "and",
      "conditions": [
        {"operator": "is_true", "left": "bullish_order_block"},
        {"operator": "<", "left": "rsi_14", "right": 40},
        {"operator": "is_true", "left": "is_accumulation"}
      ]
    }
  },
  "exit": {
    "condition": {
      "operator": ">=",
      "left": "close",
      "right": "supply_zone_low"
    }
  }
}
```
