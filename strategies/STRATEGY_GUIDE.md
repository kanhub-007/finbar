# Strategy Selection Guide & State Machine

> **How to pick the right strategy for any ticker, any market condition.**

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRE-FLIGHT CHECK (4 indicators)               │
│                                                                  │
│  compute on daily data:                                          │
│    hurst_exponent, adx, yang_zhang_vol, market_regime            │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STATE MACHINE v2                               │
│                                                                  │
│  STEP 1: Volatility gate                                         │
│  ┌─ yang_zhang_vol > 70% ───► Check if trending (STEP 2B)       │
│  │   If trending: HYPE Aggressive Long (1h SMA 10/30, wide stop) │
│  │   If NOT trending: SKIP ALL STRATEGIES                        │
│  └──────────────────────────────────────────────────────────────│
│                                                                  │
│  STEP 2A: Normal vol strategy routing                            │
│  ┌─ Hurst > 0.55 AND ADX > 22 ──────────────────────────┐       │
│  │   STATE: TRENDING (Normal Vol)                         │       │
│  │   PRIMARY: 1h AMT v3c POC Slope (dip buyer)           │       │
│  │   SECONDARY: Trend Momentum v2 (daily)                 │       │
│  └────────────────────────────────────────────────────────┘       │
│                                                                  │
│  STEP 2B: High-vol trending routing                              │
│  ┌─ Hurst > 0.55 AND ADX > 22 AND Vol > 40% ───────────┐       │
│  │   STATE: HIGH-VOL TRENDING                              │       │
│  │   PRIMARY: HYPE Aggressive Long (1h SMA 10/30)        │       │
│  │     • LONG ONLY, 1h bars, ATR 6x stop, RR 3.0         │       │
│  │     • Leverage: 1-10x, Risk: 5-20%                     │       │
│  │     • Expected: 52% WR, Sharpe 1.5                     │       │
│  │     • Best on: HYPE, high-vol crypto in uptrends       │       │
│  └────────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌─ Hurst 0.45–0.55 AND ADX 18–22 ──────────────────────┐       │
│  │   STATE: TRANSITIONAL / WEAK TREND                     │       │
│  │   PRIMARY: AMT Acceptance Trend (daily)                │       │
│  └────────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌─ ADX < 18 ───────────────────────────────────────────┐       │
│  │   STATE: NO TREND → SKIP or 1h AMT v3c if VA narrow   │       │
│  └────────────────────────────────────────────────────────┘       │
│                                                                  │
│  ┌─ Hurst < 0.45 AND ADX < 20 AND Vol < 40% ────────────┐       │
│  │   STATE: MEAN-REVERTING → Range Fade v3 (daily)       │       │
│  └────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Strategy Decision Table

| Hurst | ADX | Vol (ann) | Close vs SMA50 | → Strategy | Expected WR | Risk |
|-------|-----|-----------|:--------------:|-----------|:-----------:|------|
| >0.55 | >22 | >40% | Above | **HYPE Aggressive Long** | 52% | 5-20%, 10x |
| >0.55 | >22 | <40% | Above | **1h v3c POC Slope** | 77-100% | 5%, spot |
| >0.55 | >22 | <40% | Below | **Trend Mom v2** (short) | 40-50% | 5%, spot |
| 0.45-0.55 | 18-22 | <50% | Any | **AMT Acceptance** | 50-60% | 5-10%, spot |
| <0.45 | <20 | <40% | Any | **Range Fade v3** | 50-60% | 5%, spot |
| Any | <18 | Any | Any | **STAY OUT** or 1h v3c | — | — |

---

## Detection: "Will HYPE Strategy Work on Token X?"

```
Check 4 indicators on DAILY data:

1. hurst_exponent > 0.55
   → Token is trending (momentum works)

2. close > sma_50  
   → Token is in an UPTREND (long-only strategy)

3. adx > 22
   → Trend is STRONG enough to trade

4. yang_zhang_vol > 0.40 (40% annualized)
   → High enough vol that wide stops (6x ATR) are needed
   → Low enough vol that stops don't get blown through

ALL FOUR must be TRUE:
  ✅ → HYPE Aggressive Long (1h, SMA 10/30, ATR 6x, RR 3.0)
  ❌ → Use state machine above for other strategies
```

---

## Expected Outcomes by Ticker Archetype

| Archetype | Hurst | ADX | Vol | Strategy | WR | Return |
|-----------|-------|-----|-----|----------|:--:|:------:|
| High-Vol Trending (HYPE) | >0.60 | >25 | >60% | HYPE Aggr. Long | 52% | +87-693% |
| Blue Chip Bull (AAPL, GOOGL) | >0.60 | >25 | 15-32% | 1h v3c | 77% | +17-61% |
| Crypto Majors (BTC, ETH, SOL) | >0.60 | >25 | 39-61% | 1h v3c | 40-86% | +11-80% |
| Exchange Token (BNB) | >0.60 | >18 | 50% | 1h v3c | 79% | +28-42% |
| Meme Stock (TSLA) | ~0.56 | 16-22 | 44% | AMT Accept | 60% | +8-13% |
| Range-Bound (PLTR) | ~0.50 | <18 | 52% | STAY OUT | — | — |

---

## Test Results Summary (Jun 2026)

### Best Strategy Per Ticker

| Strategy | Ticker | Risk | Return | Sharpe | vs B&H |
|----------|--------|:----:|:------:|:------:|:------:|
| HYPE Aggr Long | HYPE | 20%,10x | +693% | 1.52 | +569% |
| HYPE Aggr Long | HYPE | 15%,10x | +422% | 1.51 | +298% |
| HYPE Aggr Long | HYPE | 10%,10x | +224% | 1.50 | +100% |
| 1h v3c | SOL | 5%,1x | +79.7% | 2.14 | +122% |
| HYPE Aggr Long | MU | 5%,1x | +69.2% | 3.94 | -258%* |
| HYPE Aggr Long | SNDK | 5%,1x | +64.8% | 3.35 | -577%* |
| 1h v3c | AAPL | 5%,1x | +61.2% | 2.66 | +14% |
| 1h v3c | BNB | 5%,1x | +42.2% | 1.40 | +69% |
| HYPE Aggr Long | HYPE | 5%,10x | +87.4% | 1.48 | -37% |
| 1h v3c | HYPE | 5%,1x | +28.9% | 1.83 | -95% |
| 1h v3c | ETH | 5%,1x | +25.9% | 1.91 | +62% |
| Trend Mom | GOOGL | 5%,1x | +24.5% | 2.61 | -21% |
| Trend Mom | BNB | 5%,1x | +12.5% | 1.20 | +40% |
| AMT Accept | TSLA | 10%,1x | +13.0% | 1.61 | -6% |

*\*MU B&H +327%, SNDK B&H +642% — strategy underperforms raw return but with vastly superior risk metrics (Sharpe 3.35-3.94)*

### Cross-Strategy Matrix (21 Tickers, All Viable Strategies)

| Ticker | Trend Mom | AMT Accept | 1h v3c | HYPE Aggr | Best |
|--------|:---------:|:----------:|:------:|:---------:|------|
| SOL | +4.4% | — | **+79.7%** | — | 1h v3c |
| AAPL | +8.3% | +3.4% | **+61.2%** | — | 1h v3c |
| BNB | +12.5% | +1.4% | **+42.2%** | — | 1h v3c |
| HYPE | -18.5% | — | +28.9% | **+693%** | HYPE Aggr |
| ETH | +10.2% | -2.8% | **+25.9%** | — | 1h v3c |
| GOOGL | **+24.5%** | -2.8% | +12.2% | — | Trend Mom |
| BTC | +11.5% | +1.7% | 0% | — | Trend Mom |
| PENDLE | +10.8% | -1.5% | — | — | Trend Mom |
| TSLA | 0% | **+7.8%** | +0.7% | — | AMT Accept |
| LINK | +3.5% | -3.5% | — | — | Trend Mom |
| MU | — | — | — | **+69.2%** | HYPE Aggr |
| SNDK | — | — | — | **+64.8%** | HYPE Aggr |
| ADA | +1.3% | — | — | — | Trend Mom |
| DOGE | +0.5% | 0 | — | — | Flat |
| SUI | -2.8% | -0.1% | — | — | Flat |
| XRP | -3.1% | -1.9% | — | — | Flat |
| AAVE | -7.2% | +0.1% | — | — | Flat |
| AVAX | -4.9% | -5.6% | — | — | Fail |
| XLM | -8.5% | — | — | — | Fail |
| NEAR | -12.5% | -0.7% | — | — | Fail |
| PLTR | 0 | 0 | — | — | No signal |

**13/21 profitable. 7 with Sharpe > 1.0. Pre-flight check filters losers before capital is risked.**

---

## ⚠️ Leverage Constraints on High-Price Stocks

The HYPE Aggressive Long strategy at 10x leverage only works on **sub-$100 assets**.
For stocks priced $500+, the wide 6x ATR stop exceeds the liquidation boundary
at 10x leverage, causing the backtester to reject all trades. Use 1-2x max for
high-price stocks.

| Asset Price | Max Leverage | Why |
|:-----------:|:------------:|-----|
| <$100 | 10x | Margin room for wide stops (HYPE, crypto) |
| $100-500 | 3-5x | Tight but workable |
| $500+ | 1-2x | Stop > liquidation distance at higher leverage |

## Strategy Files Map

```
strategies/
├── STRATEGY_GUIDE.md              ← THIS FILE (state machine)
│
├── 1h_amt_dip_buyer/              ← AMT dip buyers (mean-reversion)
│   ├── README.md                  ← AMT v1-v3c theory & detection
│   ├── README_HYPE.md             ← HYPE Aggressive Long (trend-riding)
│   ├── amt_v3c_poc_slope.yaml     ← RECOMMENDED for normal trending
│   ├── amt_v2_vol_filter.yaml
│   ├── amt_dip_buyer_final.yaml
│   └── amt_v3_wyckoff_enhanced.yaml
│
├── daily_trend/                   ← Daily trend-following
│   ├── README.md
│   ├── trend_momentum_v2.json     ← Best for GOOGL, AAPL, BNB
│   └── amt_acceptance_trend.json  ← Best for TSLA
│
├── daily_range/                   ← Low-vol range fading
│   ├── README.md
│   └── range_fade_v3.json
│
└── experimental/                  ← Needs intraday / refinement
    ├── README.md
    └── (6 strategies)

└── intraday_scalper/               ← 5min/30min/1h scalping
    ├── README.md                   ← Findings + cross-asset results
    ├── 14_amt_value_reject_30m_1h_mtf.yaml ← ⭐⭐ CURRENT BEST (MTF, SOL/HYPE + stocks)
    ├── 05_amt_value_reject_OPTIMIZED.yaml  ← Previous best (single-TF 30m)
    ├── 04_amt_value_reject_30m.json ← AMT rejection default
    ├── 13_amt_balance_breakout_30m.yaml ← ❌ Balance breakout (fails)
    ├── 01_vwap_band_fade_5m.json   ❌ loses to costs
    ├── 02_orderflow_momentum_5m.json ❌ loses to costs
    └── 03_mtf_trend_pullback_5m.json ❌ loses to costs
```

### ⭐⭐ CURRENT BEST (Jun 22, 2026): AMT Value Reject V2 (causal-validated)

The production strategy is now `15_amt_value_reject_v2.yaml` — v2 of the MTF
rejection scalper with tighter risk management (2× ATR stop, 2:1 R/R).

**ALL results below use `live_parity_streaming` (causal) enrichment** — no
lookahead bias. The old batch-mode numbers (+11,409%) were inflated by VP
lookahead and are NOT achievable in live trading.

**V2 Results (10% risk, 10x leverage, May 1 – Jun 22, Hyperliquid):**

| Symbol | Trades | WR | Return | Sharpe | Max DD | PF | Avg Trade | vs B&H |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **SOL** | 55 | 64% | **+156%** ($10K→$25.6K) | 2.06 | 40% | 1.63 | 5.6 hrs | **+167%** |
| **SUI** | 43 | 60% | **+49%** ($10K→$14.9K) | 1.09 | 33% | 1.26 | 5.4 hrs | **+70%** |

Buy & Hold comparison: SOL -10.9%, SUI -21.6% (bear market period).
The strategy profited by shorting VAH rejections during the downtrend.

**V1 vs V2 comparison (SOL, 10%/10x):**
| Version | Stop | R/R | Return | Sharpe | DD | PF |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| V1 (14_) | 3.0× ATR | 1.5 | +78% | 1.64 | 31% | 1.48 |
| **V2 (15_)** | **2.0× ATR** | **2.0** | **+156%** | **2.06** | 40% | **1.63** |

V2 doubles returns by cutting losers faster (tighter stop) and letting
winners run further (higher R/R target).

**Risk/leverage sweep (SOL V2, causal):**
| Risk | Lev | Return | Sharpe | Max DD |
|:---:|:---:|:---:|:---:|:---:|
| 2% | 3× | +25% | 1.98 | **11%** |
| 5% | 5× | +68% | **2.05** | 22% |
| 5% | 10× | +71% | 1.98 | 26% |
| 10% | 10× | +156% | 2.06 | 40% |
| 15% | 10× | +241% | **2.23** | 45% |

Sweet spot for live: **5%/5×** (Sharpe 2.05, DD 22%, +68%).
Aggressive: **15%/10×** (+241%, Sharpe 2.23, but 45% DD = near-liquidation risk).

A Balance→Breakout variant (narrow-VA breakout) was tested and failed (-32% HYPE).
See `intraday_scalper/README.md` for full risk-spectrum results.

### ⭐ NEW (Jun 2026): Intraday Scalper Research

Tested 4 scalper archetypes on HYPE/BTC/ETH across 5min/30min/1h **with realistic
costs** (5bp+5bp). Only one edge survived:

| Archetype | TF | Result | Lesson |
|---|:--:|---|---|
| **AMT Value Rejection** | 30m/1h | ✅ HYPE +42-96%, Sharpe 6-10, DD<5% | Session VP edges are predictive |
| VWAP Band Fade | 5m | ❌ -6% | Chopped up by noise |
| Order-Flow Momentum | 5m | ❌ -24% | BVC ratio not predictive at 5m |
| MTF Trend Pullback | 5m | ❌ -19% | Pullbacks keep extending |

**Use `intraday_scalper/05_amt_value_reject_OPTIMIZED.yaml` for HYPE intraday.**
It is HYPE-tuned (BTC/ETH are too low-frequency for this specific signal — see
their README). All 5m pure-scalping approaches lose once costs are applied.```
