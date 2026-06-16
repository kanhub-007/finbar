# Trading Theories — Supported Indicators & Usage

> Finbar supports six trading-theory frameworks beyond standard technical
> analysis. This guide covers the concrete indicators available for each theory,
> how they're computed, and how to use them in strategy JSON definitions.

---

## Table of Contents

1. [Wyckoff / Volume Spread Analysis (VSA)](#1-wyckoff--volume-spread-analysis-vsa)
2. [Smart Money Concepts (SMC / ICT)](#2-smart-money-concepts-smc--ict)
3. [Supply & Demand Zones](#3-supply--demand-zones)
4. [Fibonacci Tools](#4-fibonacci-tools)
5. [Bill Williams / Chaos Theory](#5-bill-williams--chaos-theory)
6. [Auction Market Theory (AMT)](#6-auction-market-theory-amt)
7. [Multi-Theory Strategy Examples](#7-multi-theory-strategy-examples)

---

## 1. Wyckoff / Volume Spread Analysis (VSA)

Richard Wyckoff's methodology analyzes price action, volume, and the
relationship between them to identify institutional accumulation and
distribution cycles.

### Core Concepts

The market moves through four phases: **Accumulation → Markup → Distribution
→ Markdown**. VSA indicators detect these phases and the specific bar-by-bar
signals that confirm or refute them.

### Wyckoff Phase Classification

| Indicator | Output | Description |
|-----------|--------|-------------|
| `wyckoff_phase` | `ACCUMULATION`, `MARKUP`, `DISTRIBUTION`, `MARKDOWN`, `NEUTRAL` | Current phase |
| `is_accumulation` | bool | True when accumulation detected |
| `is_distribution` | bool | True when distribution detected |
| `is_markup` | bool | True during markup (uptrend) |
| `is_markdown` | bool | True during markdown (downtrend) |
| `is_wyckoff_neutral` | bool | True in neutral/transitional phase |

### VSA Bar-by-Bar Signals

These detect specific Wyckoff events from OHLCV on every bar:

| Indicator | What it detects | Trading implication |
|-----------|----------------|---------------------|
| `stopping_volume` | High volume halting a decline | Potential accumulation. Look for long entries. |
| `climax_volume` | Ultra-high volume at market extreme | Selling climax (bottom) or buying climax (top). Reversal signal. |
| `no_demand` | Declining volume on an up bar | Weak rally — no institutional support. Short or exit longs. |
| `no_supply` | Declining volume on a down bar | Weak selling — no institutional pressure. Long or exit shorts. |
| `effort_to_rise` | High volume + wide up range | Genuine buying effort. Bullish. |
| `effort_to_fall` | High volume + wide down range | Genuine selling effort. Bearish. |
| `effort_result_divergence` | High volume + small range | Absorption — smart money taking the other side. Major reversal signal. |
| `bag_holding` | Long upper shadow on high volume | Trapped longs — selling into strength. Bearish. |
| `shakeout` | Sudden drop + recovery on high volume | Spring / Upthrust pattern. Institutions forcing stops before reversing. |
| `vsa_test_signal` | Low-volume probe of support | Successful test — smart money confirming support holds. Bullish. |

### Trend Structure

| Indicator | Description |
|-----------|-------------|
| `volume_trend_confirmation` | Volume direction aligned with price trend — confirms trend health |
| `trend_phase` | Wyckoff trend phase classification |
| `coil_intensity` | Compression building before expansion |
| `is_coiled` | Binary: market is coiled for breakout |

### Strategy JSON — Wyckoff Example

```json
{
  "parameters": {
    "atr_period": {"type": "int", "default": 14}
  },
  "indicators": [
    {"alias": "atr_14", "concrete": "atr", "params": {"period": 14}},
    {"alias": "wyckoff_phase", "concrete": "wyckoff_phase"},
    {"alias": "effort_result_divergence", "concrete": "effort_result_divergence"},
    {"alias": "stopping_volume", "concrete": "stopping_volume"},
    {"alias": "no_demand", "concrete": "no_demand"},
    {"alias": "shakeout", "concrete": "shakeout"}
  ],
  "risk": {
    "stop_loss": {"type": "atr", "multiplier": 2.0},
    "take_profit": {"type": "risk_reward", "ratio": 3.0}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "is_true", "left": "is_accumulation"},
          {"operator": "is_true", "left": "stopping_volume"}
        ]
      },
      "exit": {
        "operator": "is_true",
        "left": "no_demand"
      }
    },
    "short": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "is_true", "left": "is_distribution"},
          {"operator": "is_true", "left": "effort_to_fall"}
        ]
      },
      "exit": {
        "operator": "is_true",
        "left": "stopping_volume"
      }
    }
  }
}
```

### Key Wyckoff Rules

1. **Effort vs. Result**: Wide range + high volume = effort confirmed. Wide
   range + low volume = effort not confirmed (weak). Narrow range + high
   volume = absorption (effort_result_divergence = potential reversal).
2. **No Demand / No Supply on Tests**: After a decline, a low-volume test of
   support (vsa_test_signal) is the strongest bullish signal in VSA.
3. **Spring / Shakeout**: A sudden break below support that immediately
   recovers on high volume is an accumulation spring — enter long.

---

## 2. Smart Money Concepts (SMC / ICT)

SMC interprets price action through the lens of institutional order flow.
Key concepts: structure breaks, liquidity sweeps, order blocks, fair value
gaps, and premium/discount zones.

### Structure

| Indicator | Output | Description |
|-----------|--------|-------------|
| `bos` | bool | Break of Structure — price breaks a recent swing high/low in the trend direction. Trend continuation. |
| `choch` | bool | Change of Character — price breaks a swing point opposite the trend. Potential reversal. |

**Interpretation:**
- In an uptrend: BOS = break above previous swing high. Continuation.
- In an uptrend: CHOCH = break below previous swing low. Potential reversal.
- CHOCH confirmation requires the break to hold (no immediate reclaim).

### Liquidity Sweeps

| Indicator | Output | Description |
|-----------|--------|-------------|
| `liquidity_sweep_high` | bool | Price sweeps above a recent swing high then reverses. Buyside liquidity taken. |
| `liquidity_sweep_low` | bool | Price sweeps below a recent swing low then reverses. Sellside liquidity taken. |

**Strategy use:** Liquidity sweeps often precede the real move. A sweep of
sellside liquidity (below a swing low) that immediately reverses is a
classic SMC long entry — "smart money" took out stops before going long.

### Order Blocks

| Indicator | Output | Description |
|-----------|--------|-------------|
| `bullish_order_block` | bool | Last down candle before an uptrend began. Acts as demand/support. |
| `bearish_order_block` | bool | Last up candle before a downtrend began. Acts as supply/resistance. |
| `breaker_block_bullish` | bool | A bearish OB that was broken and reclaimed as support. Stronger signal. |
| `breaker_block_bearish` | bool | A bullish OB that was broken and reclaimed as resistance. Stronger signal. |

**Strategy use:** Price often returns to test order blocks. A bullish OB
retest with confirmation is a high-probability long entry. Breaker blocks
are stronger — a failed OB flipped to the opposite role.

### Fair Value Gaps (Imbalances)

| Indicator | Output | Description |
|-----------|--------|-------------|
| `bullish_fvg` | bool | Gap between wicks where buying overwhelmed selling. Support zone. |
| `bearish_fvg` | bool | Gap between wicks where selling overwhelmed buying. Resistance zone. |

**Strategy use:** Price tends to return to fill FVGs (rebalancing). Enter
on the retest in the direction of the original imbalance.

### Premium/Discount Zones

| Indicator | Output | Description |
|-----------|--------|-------------|
| `premium_discount_zone` | str | `PREMIUM` (above 50% of range), `EQUILIBRIUM` (near 50%), `DISCOUNT` (below 50%) |

**Strategy use:** In an uptrend, buy in discount, sell in premium. Never
chase entries in premium.

### Strategy JSON — SMC Example

```json
{
  "indicators": [
    {"alias": "bos", "concrete": "bos"},
    {"alias": "choch", "concrete": "choch"},
    {"alias": "sweep_low", "concrete": "liquidity_sweep_low"},
    {"alias": "sweep_high", "concrete": "liquidity_sweep_high"},
    {"alias": "bullish_ob", "concrete": "bullish_order_block"},
    {"alias": "bearish_ob", "concrete": "bearish_order_block"},
    {"alias": "bullish_fvg", "concrete": "bullish_fvg"},
    {"alias": "bearish_fvg", "concrete": "bearish_fvg"},
    {"alias": "zone", "concrete": "premium_discount_zone"},
    {"alias": "ema_50", "concrete": "ema_50"}
  ],
  "risk": {
    "stop_loss": {"type": "atr", "multiplier": 1.5},
    "take_profit": {"type": "risk_reward", "ratio": 2.0}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "is_true", "left": "sweep_low"},
          {"operator": "is_true", "left": "bullish_ob"},
          {"operator": "==", "left": "zone", "right": "DISCOUNT"}
        ]
      },
      "exit": {
        "operator": "or",
        "conditions": [
          {"operator": "is_true", "left": "choch"},
          {"operator": "==", "left": "zone", "right": "PREMIUM"}
        ]
      }
    }
  }
}
```

---

## 3. Supply & Demand Zones

Supply and demand zones identify price levels where institutional buying
(demand) or selling (supply) created significant reversals. Unlike
horizontal support/resistance, zones have width (a price range) and a
quality score.

### Zone Boundaries & Quality

| Indicator | Description |
|-----------|-------------|
| `demand_zone_low` | Lower boundary of nearest active demand zone |
| `demand_zone_high` | Upper boundary of nearest active demand zone |
| `demand_zone_score` | Quality score (0–100) — freshness, reaction strength, time at level |
| `supply_zone_low` | Lower boundary of nearest active supply zone |
| `supply_zone_high` | Upper boundary of nearest active supply zone |
| `supply_zone_score` | Quality score (0–100) |

### Zone Signals & Failures

| Indicator | Description |
|-----------|-------------|
| `zone_signal` | Combined zone interaction signal (price approaching/at/breaking zone) |
| `zone_failure_bullish` | Supply zone broken to the upside — becomes demand |
| `zone_failure_bearish` | Demand zone broken to the downside — becomes supply |

**Key principles:**
- Higher quality score = stronger zone. Score factors: number of touches,
  strength of the reversal, time since formation, volume at the level.
- Fresh zones (untested) are stronger than zones that have been tested
  multiple times.
- A zone failure is a flip signal: failed supply → demand, failed demand →
  supply.

### Strategy JSON — Supply/Demand Example

```json
{
  "indicators": [
    {"alias": "demand_low", "concrete": "demand_zone_low"},
    {"alias": "demand_score", "concrete": "demand_zone_score"},
    {"alias": "supply_high", "concrete": "supply_zone_high"},
    {"alias": "supply_score", "concrete": "supply_zone_score"},
    {"alias": "zone_fail_bull", "concrete": "zone_failure_bullish"},
    {"alias": "rsi_14", "concrete": "rsi_14"}
  ],
  "risk": {
    "stop_loss": {"type": "fixed_pct", "value": 2.0},
    "take_profit": {"type": "risk_reward", "ratio": 3.0}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "<=", "left": "close", "right": "demand_low"},
          {"operator": ">=", "left": "demand_score", "right": 60},
          {"operator": "<", "left": "rsi_14", "right": 40}
        ]
      },
      "exit": {
        "operator": ">=",
        "left": "close",
        "right": "supply_high"
      }
    }
  }
}
```

---

## 4. Fibonacci Tools

Fibonacci retracement and extension levels calculated from recent swing
highs and lows. These are price levels, not boolean signals — use them
in conditions comparing price to the level.

### Levels

| Indicator | Value | Description |
|-----------|-------|-------------|
| `fib_382_retrace` | Price level | 38.2% retracement from recent major swing |
| `fib_500_retrace` | Price level | 50% retracement (midpoint) |
| `fib_618_retrace` | Price level | 61.8% retracement (golden ratio) |
| `fib_1618_extension` | Price level | 161.8% extension beyond the swing range |

### Confluence

| Indicator | Description |
|-----------|-------------|
| `fib_confluence_score` | 0–100 score where multiple Fibonacci levels cluster. High score = strong zone. |

**Strategy use:**
- Retracements: Enter at 50% or 61.8% pullback of the prior trend move.
- Extensions: Take profit at 161.8% extension of the prior swing.
- Confluence: When Fibonacci levels overlap with supply/demand zones or
  order blocks, the zone is significantly stronger.

### Strategy JSON — Fibonacci Example

```json
{
  "indicators": [
    {"alias": "fib_618", "concrete": "fib_618_retrace"},
    {"alias": "fib_ext", "concrete": "fib_1618_extension"},
    {"alias": "fib_conf", "concrete": "fib_confluence_score"},
    {"alias": "demand_score", "concrete": "demand_zone_score"},
    {"alias": "sma_50", "concrete": "sma_50"}
  ],
  "risk": {
    "stop_loss": {"type": "fixed_pct", "value": 2.0},
    "take_profit": {"type": "risk_reward", "ratio": 2.5}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "<=", "left": "close", "right": "fib_618"},
          {"operator": ">=", "left": "fib_conf", "right": 50},
          {"operator": ">", "left": "close", "right": "sma_50"}
        ]
      },
      "exit": {
        "operator": ">=",
        "left": "close",
        "right": "fib_ext"
      }
    }
  }
}
```

---

## 5. Bill Williams / Chaos Theory

Williams' trading system uses fractal geometry, the Alligator, and momentum
oscillators to identify market phases and trade signals.

### Alligator (Trend Detection)

| Indicator | Period | Description |
|-----------|--------|-------------|
| `alligator_jaw` | 13 (shift 8) | Blue line — slowest, defines the trend |
| `alligator_teeth` | 8 (shift 5) | Red line — medium speed |
| `alligator_lips` | 5 (shift 3) | Green line — fastest, entry timing |
| `alligator_status` | — | SLEEPING (lines intertwined), AWAKENING (crossing), EATING (diverged) |

**Strategy use:**
- Sleeping: Market is ranging. Do not trade.
- Awakening: A signal is forming. Prepare.
- Eating: Alligator is open. Trend is active. Trade in the direction.

### Momentum Oscillators

| Indicator | Description |
|-----------|-------------|
| `awesome_oscillator` | AO: 5-period SMA − 34-period SMA of bar midpoints. Measures market momentum. |
| `accelerator_oscillator` | AC: AO − 5-period SMA of AO. Measures acceleration of momentum (early warning). |

**Williams signals:**
- AO crosses above zero = bullish. Below zero = bearish.
- AO saucer (3 consecutive bars with higher AO) = bullish setup.
- AC changes sign before AO — early reversal warning.
- Zone signal: AO and AC same color + same direction = strong momentum.

### Fractals

| Indicator | Description |
|-----------|-------------|
| `williams_fractal_high` | 5-bar pattern: middle bar has highest high. Resistance level. |
| `williams_fractal_low` | 5-bar pattern: middle bar has lowest low. Support level. |

**Strategy use:** Fractals are the "breakout levels" in Williams' system.
A fractal break above an Alligator jaw = buy signal. A fractal break below
= sell signal.

### Fractal Market Hypothesis

| Indicator | Range | Description |
|-----------|-------|-------------|
| `hurst_exponent` | 0.0–1.0 | H<0.5 = mean-reverting. H=0.5 = random walk. H>0.5 = trending/persistent. |
| `fractal_regime` | string | Fractal-based regime classification |

**Strategy use:** Select strategy type based on Hurst:
- H < 0.4 → mean reversion strategies (Bollinger Bands, RSI extremes).
- 0.4 ≤ H ≤ 0.6 → range-bound or avoid.
- H > 0.6 → trend-following strategies (MA crossovers, breakouts).

### Strategy JSON — Alligator + Fractals Example

```json
{
  "indicators": [
    {"alias": "jaw", "concrete": "alligator_jaw"},
    {"alias": "teeth", "concrete": "alligator_teeth"},
    {"alias": "lips", "concrete": "alligator_lips"},
    {"alias": "status", "concrete": "alligator_status"},
    {"alias": "fractal_high", "concrete": "williams_fractal_high"},
    {"alias": "fractal_low", "concrete": "williams_fractal_low"},
    {"alias": "ao", "concrete": "awesome_oscillator"}
  ],
  "risk": {
    "stop_loss": {"type": "atr", "multiplier": 2.0},
    "take_profit": {"type": "risk_reward", "ratio": 3.0}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "==", "left": "status", "right": "EATING"},
          {"operator": ">", "left": "close", "right": "jaw"},
          {"operator": ">", "left": "close", "right": "fractal_high"},
          {"operator": ">", "left": "ao", "right": 0}
        ]
      },
      "exit": {
        "operator": "or",
        "conditions": [
          {"operator": "<", "left": "close", "right": "teeth"},
          {"operator": "<", "left": "ao", "right": 0}
        ]
      }
    }
  }
}
```

---

## 6. Auction Market Theory (AMT)

AMT is covered in detail in [`QUANTITATIVE_PROXIES.md`](QUANTITATIVE_PROXIES.md).
This section provides a quick reference to the available AMT indicators.

### VWAP Bands (intraday only)

`vwap_session`, `vwap_upper_1`, `vwap_lower_1`, `vwap_upper_2`, `vwap_lower_2`

### Volume Profile

`vp_poc`, `vp_vah`, `vp_val`, plus rolling composites: `vp_poc_Nd`,
`cvp_poc_Nd` (stacked), `rvp_poc_N` (bar-window).

### Market Profile (TPO)

`mp_poc`, `mp_vah`, `mp_val`

### Auction State

`inside_value`, `above_value`, `below_value`, `at_poc`, `near_vah`,
`near_val`, `balance_status`

### AMT Rules

`acceptance_into_value`, `rejection_from_edge`, `acceptance_outside_value`,
`poc_rejection`, `edge_volume_building`, `value_area_migration`

### Profile Shape

`profile_shape`, `is_normal_shape`, `is_p_shape`, `is_b_shape`,
`is_d_shape`, `is_neutral_shape`, `day_type_classification`

---

## 7. Multi-Theory Strategy Examples

The real power comes from combining indicators across theories. Here are two
examples.

### Wyckoff + AMT (Accumulation Breakout)

Enter when Wyckoff detects accumulation AND AMT confirms acceptance above value.

```json
{
  "indicators": [
    {"alias": "is_acc", "concrete": "is_accumulation"},
    {"alias": "effort_div", "concrete": "effort_result_divergence"},
    {"alias": "above_value", "concrete": "above_value"},
    {"alias": "acceptance_out", "concrete": "acceptance_outside_value"},
    {"alias": "sma_50", "concrete": "sma_50"},
    {"alias": "rvol", "concrete": "rvol"}
  ],
  "risk": {
    "stop_loss": {"type": "atr", "multiplier": 2.5},
    "take_profit": {"type": "risk_reward", "ratio": 3.0}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "is_true", "left": "is_acc"},
          {"operator": "is_true", "left": "acceptance_out"},
          {"operator": ">", "left": "rvol", "right": 1.5},
          {"operator": ">", "left": "close", "right": "sma_50"}
        ]
      },
      "exit": {
        "operator": "is_true",
        "left": "effort_div"
      }
    }
  }
}
```

### SMC + Supply/Demand + Fibonacci

Enter when price sweeps sellside liquidity into a high-quality demand zone
that aligns with a 61.8% Fibonacci retracement.

```json
{
  "indicators": [
    {"alias": "sweep_low", "concrete": "liquidity_sweep_low"},
    {"alias": "demand_high", "concrete": "demand_zone_high"},
    {"alias": "demand_score", "concrete": "demand_zone_score"},
    {"alias": "fib_618", "concrete": "fib_618_retrace"},
    {"alias": "fib_conf", "concrete": "fib_confluence_score"},
    {"alias": "bullish_ob", "concrete": "bullish_order_block"}
  ],
  "risk": {
    "stop_loss": {"type": "atr", "multiplier": 1.5},
    "take_profit": {"type": "risk_reward", "ratio": 3.5}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "and",
        "conditions": [
          {"operator": "is_true", "left": "sweep_low"},
          {"operator": "<=", "left": "close", "right": "demand_high"},
          {"operator": ">=", "left": "demand_score", "right": 50},
          {"operator": "<=", "left": "close", "right": "fib_618"},
          {"operator": ">=", "left": "fib_conf", "right": 40}
        ]
      },
      "exit": {
        "operator": "is_true",
        "left": "bullish_ob"
      }
    }
  }
}
```

### Regime-Adaptive Strategy (Hurst + Theory Selection)

Use the Hurst exponent to switch between mean reversion and momentum:

```json
{
  "indicators": [
    {"alias": "hurst", "concrete": "hurst_exponent"},
    {"alias": "rsi_14", "concrete": "rsi_14"},
    {"alias": "sma_20", "concrete": "sma_20"},
    {"alias": "sma_50", "concrete": "sma_50"},
    {"alias": "bb_lower", "concrete": "bb_lower"},
    {"alias": "bb_middle", "concrete": "bb_middle"},
    {"alias": "bb_upper", "concrete": "bb_upper"}
  ],
  "risk": {
    "stop_loss": {"type": "atr", "multiplier": 2.0},
    "take_profit": {"type": "risk_reward", "ratio": 2.0}
  },
  "sides": {
    "long": {
      "entry": {
        "operator": "or",
        "conditions": [
          {
            "operator": "and",
            "conditions": [
              {"operator": "<", "left": "hurst", "right": 0.4},
              {"operator": "<=", "left": "close", "right": "bb_lower"},
              {"operator": "<", "left": "rsi_14", "right": 30}
            ]
          },
          {
            "operator": "and",
            "conditions": [
              {"operator": ">", "left": "hurst", "right": 0.6},
              {"operator": "crosses_above", "left": "sma_20", "right": "sma_50"}
            ]
          }
        ]
      },
      "exit": {
        "operator": "or",
        "conditions": [
          {"operator": ">=", "left": "close", "right": "bb_middle"},
          {"operator": "crosses_below", "left": "sma_20", "right": "sma_50"}
        ]
      }
    }
  }
}
```

---

## Theory Coverage Summary

| Theory | Indicators | Best data | Key signals |
|--------|:---:|-----------|-------------|
| **Wyckoff / VSA** | 18 | Daily, 1h | Phase detection, effort/result, stopping volume |
| **SMC / ICT** | 11 | 1h, 30m | Structure breaks, liquidity sweeps, order blocks |
| **Supply & Demand** | 9 | Daily, 1h | Zone boundaries, quality scores, failures |
| **Fibonacci** | 5 | Any | Retracement/extension levels, confluence |
| **Bill Williams** | 8 | Daily, 1h | Alligator phases, fractals, AO/AC |
| **AMT** | 50+ | 30m, 1h best | Value areas, auction states, AMT rule signals |
| **Fractal / Regime** | 3 | Daily, 1h | Hurst exponent, fractal/market regime |

> **See also:** [`METRIC_CATALOG.md`](METRIC_CATALOG.md) for the complete
> reference of all 219 indicators, organized by family with data class
> compatibility. [`QUANTITATIVE_PROXIES.md`](QUANTITATIVE_PROXIES.md) for
> AMT depth and daily-to-intraday proxy estimators.
