# Quantitative Trading Proxies

> Proxies are industry-standard mathematical models used to simulate intraday
> market structure metrics from daily OHLCV data when tick/1-minute data is
> unavailable for historical backtests.

Finbar implements the following established standards.

---

## 1. Intraday Structure Proxies

### Typical Price as VWAP Proxy

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| VWAP (Volume Weighted Average Price) | Typical Price `(H+L+C)/3` | `proxy_vwap` |

VWAP is the "fair value" of a session. Without intraday volume distribution,
Typical Price provides the statistical mean of the day's range. Academic studies
show >0.95 correlation with intraday VWAP on normal/trend days.

```
compute_indicators("AAPL", "1d", ["proxy_vwap", "sma_50"])
```

### Daily Open as Initial Balance (IB) Proxy

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| IB High (first 60 min high) | Open + 0.1 × ATR | `proxy_ib_high` |
| IB Low (first 60 min low) | Open − 0.1 × ATR | `proxy_ib_low` |

In Auction Market Theory, a trend day occurs when price opens at one extreme
and closes at the other. The volatility buffer ensures signals only trigger on
significant breakouts from the opening price discovery.

```
compute_indicators("AAPL", "1d", ["proxy_vwap", "sma_50", "atr"])
```

Requires `atr` indicator to compute `proxy_ib_high/low`.

---

## 2. Volatility & Options Proxies

### ATR as Implied Volatility Proxy

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| Implied Volatility (IV) | 0.8 × ATR | `proxy_expected_move` |
| Implied Volatility (IV) | (ATR/Price) × √252 | `proxy_iv` |

### Parkinson Volatility

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| Standard Deviation | `√(ln(H/L)² / (4·ln(2)))` | `proxy_parkinson` |

Parkinson Volatility uses the High-Low range, capturing intraday hidden
volatility that standard (close-to-close) measures miss.

### Garman-Klass & Rogers-Satchell

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| Standard Deviation | Garman-Klass (OHLC-based) | `proxy_garman_klass` |
| Standard Deviation | Rogers-Satchell (drift-aware) | `proxy_rogers_satchell` |

---

## 3. Institutional Presence Proxies

### Internal Bar Strength (IBS) — "Closing Drive"

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| Institutional Accumulation | `(C−L) / (H−L)` | `proxy_ibs` |

IBS > 0.8 suggests institutions defended the tape and bought into the close.

### Relative Volume (RVOL)

| Actual Metric | Proxy | Finbar Column |
|---|---|---|
| Dark Pool / Institutional Sweep | `Volume / SMA(Volume, 20)` | Via `rvol` indicator |

RVOL > 1.5 is the standard proxy for institutional participation.

---

## 4. Not Supported (Future Candidates)

| Actual Metric | Standard Proxy | Status |
|---|---|---|
| Liquidity Walls | Round number clusters | Not implemented |
| Market Impact | 0.0001 × Volume Ratio | Not implemented |
| Copper/Gold Ratio | Macro risk-on/off | Not implemented |
| High-Beta / Low-Beta | Speculative heat ratio | Not implemented |

---

## Usage

### On daily data (proxies needed)

```
compute_indicators("AAPL", "1d", [
    "proxy_vwap",     # typical price — VWAP substitute
    "sma_50",          # 50-day trend
    "sma_200",         # 200-day trend
    "atr",             # required for proxy_ib_* and proxy_expected_move
    "rvol"             # institutional participation
])
```

Requesting `proxy_vwap` or `proxy_atr` triggers ALL proxy columns as a batch
computation (side effect of the caching layer).

### On intraday data (no proxies needed)

```
compute_indicators("AAPL", "1h", [
    "vwap",    # real VWAP from intraday volume
    "ibs",     # real IBS from intraday bars
    "rvol",    # real relative volume
    "atr",
    "sma_50",
    "sma_200"
])
```

---

## Auction Market Theory (AMT) Indicators

Finbar implements the full Auction Market Theory framework described in
[TradingRiot's AMT guide](https://blog.tradingriot.com/p/auction-market-theory).
All indicators are computable from OHLCV bars — no tick data needed.

### VWAP Standard Deviation Bands

Session-scoped VWAP with 1σ and 2σ bands. Unlike the continuous `vwap`
(pandas_ta), these reset each calendar day.

| Column | Description |
|--------|-------------|
| `vwap_session` | Session-scoped cumulative VWAP |
| `vwap_upper_1` | VWAP + 1σ |
| `vwap_lower_1` | VWAP − 1σ |
| `vwap_upper_2` | VWAP + 2σ |
| `vwap_lower_2` | VWAP − 2σ |

Best on: **30min / 1h**. On daily bars, std = 0 (single point) — use rolling
composites instead.

### Volume Profile (Proxy)

Approximate POC/VAH/VAL using Parkinson-weighted normal distribution within
each bar. 68% Value Area captured via greedy expansion from POC.

| Column | Description |
|--------|-------------|
| `vp_poc` | Point of Control — price with most volume |
| `vp_vah` | Value Area High — 68% volume zone top |
| `vp_val` | Value Area Low — 68% volume zone bottom |
| `vp_poc_Nd` | Rolling N-session median of POC (any N, e.g. `vp_poc_10d`) |
| `vp_vah_Nd` | Rolling N-session median of VAH |
| `vp_val_Nd` | Rolling N-session median of VAL |

Best on: **30min / 1h** (multi-bar sessions). On daily bars, each bar = one
session, producing POC ≈ typical price, VAH ≈ high, VAL ≈ low. Rolling
composites (`vp_poc_5d`, `vp_poc_20d`) restore multi-day utility on daily data.

### Market Profile (TPO)

Time-at-Price based POC/VAH/VAL. Counts 30-minute periods where each price
level was "visited" (bar range overlap). The original Steidlmayer/CBOT tool.

| Column | Description |
|--------|-------------|
| `mp_poc` | Point of Control — price with most TPOs (time) |
| `mp_vah` | Value Area High — 68% TPO zone top |
| `mp_val` | Value Area Low — 68% TPO zone bottom |

VP (volume) vs MP (time): VP uses volume distribution, MP uses time counts.
POC typically differs by 0.2-1.2%. The article notes volume matters more in
electronic markets, but MP provides the original AMT perspective.

### Auction State Classifiers

Derived from Volume Profile: answers "where is price relative to value?"

| Column | Type | Description |
|--------|------|-------------|
| `inside_value` | bool | Close between VAL and VAH |
| `above_value` | bool | Close above VAH |
| `below_value` | bool | Close below VAL |
| `at_poc` | bool | Close within 2% of value area width from POC |
| `near_vah` | bool | Close within 10% of VAH |
| `near_val` | bool | Close within 10% of VAL |
| `distance_to_vah_pct` | float | (VAH − close) / VAH × 100 |
| `distance_to_val_pct` | float | (close − VAL) / close × 100 |
| `value_area_width_pct` | float | (VAH − VAL) / VAH × 100 |
| `balance_status` | str | BALANCED \| IMBALANCED_UP \| IMBALANCED_DOWN |

Balance detection: BALANCED = inside value AND width < 1.5×ATR.
IMBALANCED = outside value, or inside but wide with directional bias.

### AMT Rule Signals

Encode the 5 Auction Market Theory rules as boolean signals. No forward-looking
bias — all signals use past/current bar data only.

| Column | Rule | Signal |
|--------|------|--------|
| `acceptance_into_value` | Rule 1 | Price enters value from outside |
| `rejection_from_edge` | Rule 2 | Price touches VAH/VAL and reverses (IBS) |
| `acceptance_outside_value` | Rule 3 | Price leaves value → seeks new fair value |
| `poc_rejection` | Rule 4 | Strong reversal at POC (disrupts rotation) |
| `edge_volume_building` | Rule 5 | Volume accumulating at edge (breakout setup) |
| `value_area_migration` | — | POC trend: HIGHER \| LOWER \| STABLE |

### Usage

```python
# Compute a full AMT pipeline
compute_indicators(
    symbol="AAPL",
    source="yfinance",
    interval="30min",
    indicators_json='["vwap","rvol","atr",'
                    '"vp_poc","vp_vah","vp_val",'
                    '"vp_poc_5d","vp_vah_5d","vp_val_5d",'
                    '"mp_poc","mp_vah","mp_val",'
                    '"inside_value","balance_status",'
                    '"acceptance_outside_value","edge_volume_building"]',
    start_date="2026-04-01",
)
```

**Data quality:** These are OHLCV-based approximations — not tick-level
exchange profiles. POC accuracy: ±1-2% for liquid assets. VAH/VAL accuracy:
±3-5%. Best results on 30min/1h intraday data; use rolling composites on daily.
