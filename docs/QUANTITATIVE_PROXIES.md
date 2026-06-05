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

## Why Proxies Work

Markets are **fractal**. The behavior seen in a 5-minute Initial Balance breakout
is mirrored in the relationship between a Daily Open and a Daily Close. By using
these established standards, you can build strategies that capture institutional
logic using only retail data.
