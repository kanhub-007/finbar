# strategy-runtime

> Strategy definition parser, condition evaluator, risk calculator, and
> technical indicator engine — a reusable runtime for JSON/YAML trading
> strategy definitions.

[![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)](https://www.python.org/)
[![Schema](https://img.shields.io/badge/strategy_schema-2.0-green)](#strategy-schema-version)

---

## Overview

`strategy-runtime` provides a complete pipeline for executing rule-based trading
strategies defined in JSON or YAML:

```
YAML/JSON definition  ──►  Parser  ──►  StrategyDefinition
                                              │
                    ┌─────────────────────────┘
                    ▼
              Indicator Calculator  ──►  Enriched bars
                                              │
                    ┌─────────────────────────┘
                    ▼
              Condition Evaluator  ──►  Entry/exit signals
                    │
                    ▼
              Risk Calculator  ──►  Stop-loss & take-profit prices
```

The package is **application-agnostic**: it parses strategies, enriches market
data with technical indicators, evaluates condition trees, and computes risk
prices — then stops. It does not fetch data, submit orders, persist to
databases, or start servers. Use it as the runtime engine inside a backtester,
a live trading bot, a strategy validator, or an analytics dashboard.

---

## Installation

```bash
# Core package (parser + evaluator, no data-science deps)
pip install strategy-runtime

# From a local path (no PyPI upload needed)
pip install /absolute/path/to/packages/strategy-runtime
pip install -e /absolute/path/to/packages/strategy-runtime   # editable

# In pyproject.toml of a consuming project:
# "strategy-runtime @ file:///../packages/strategy-runtime"

# With YAML support
pip install strategy-runtime[yaml]

# Full install (indicators, pandas, numpy)
pip install strategy-runtime[pandas,yaml]

# Development
pip install strategy-runtime[dev]
```

### Python version

Requires **Python ≥ 3.12**. The `[pandas]` extra additionally requires
`numpy`, `pandas`, and `pandas-ta` (which depends on `numba`; Python < 3.14).

---

## Package structure

```
finbar_strategy_runtime/
├── domain/
│   ├── entities/          # 32 pure dataclasses/enums — no framework deps
│   ├── interfaces/        # 13 ABCs — contracts for DI
│   └── services/          # Pure math functions (numpy/pandas, no I/O)
├── parser/                # YAML/JSON loader, validators, serializers
├── evaluation/            # Condition evaluator, rule-based strategy, risk calc
└── indicators/            # Pandas-backed indicator calculator [pandas extra]
```

---

## Quick start

### Parse a strategy

```python
from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
)

parser = StrategyDefinitionParser()

# Parse YAML
result = parser.parse("""
schema_version: "2.0"
name: sma_crossover
description: Simple SMA crossover strategy
indicators:
  - name: sma_fast
    type: sma
    period: 10
  - name: sma_slow
    type: sma
    period: 30
sides:
  long:
    entry:
      condition:
        operator: crosses_above
        left: sma_fast
        right: sma_slow
    exit:
      condition:
        operator: crosses_below
        left: sma_fast
        right: sma_slow
""")

if result.valid:
    print(f"Strategy: {result.definition.name}")
    print(f"Required indicators: {result.required_indicators}")
else:
    for err in result.errors:
        print(f"  {err.path}: {err.message}")
```

### Compute indicators

```python
import pandas as pd
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)

calc = PandasTaIndicatorCalculator()
df = pd.DataFrame(...)  # OHLCV bars with datetime index

enriched = calc.calculate(df, ["rsi_14", "sma_20", "sma_50", "atr"])
# enriched now has columns: open, high, low, close, volume,
#   rsi_14, sma_20, sma_50, atr
```

### Evaluate a strategy against market data

```python
from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
)

# definition comes from the parser result above
strategy = JsonRuleBasedStrategy(result.definition)

# Feed bars one at a time; crossover state persists across calls
for bar in enriched_bars:
    signal = strategy.on_bar(bar, position)
    print(f"Action: {signal.action}, Direction: {signal.direction}")
    print(f"  Stop: {signal.stop_price}, Target: {signal.target_price}")

# Reset state between independent runs
strategy.on_reset()
```

---

## Domain model

### Strategy definition entities

| Entity | Description |
|--------|-------------|
| `StrategyDefinition` | Root parsed strategy — name, parameters, indicators, features, risk, sides |
| `StrategyParameter` | Typed runtime parameter with min/max bounds and default value |
| `IndicatorSpec` | Declares one indicator column (name, type, period, timeframe) |
| `FeatureSpec` | Derived feature declaration (source, window, shift, expression) |
| `FormulaNode` | Expression AST for formula-based features |
| `RiskSpec` | Risk settings — stop-loss type, take-profit type, multipliers, ratios |
| `TimeframeDeclaration` | Primary interval + up to 3 informative timeframes with aliases |
| `SideRules` | Entry/exit condition trees for long/short sides |
| `ConditionGroup` | Nested boolean tree node (all / any / not / condition) |
| `Condition` | Atomic comparison — left operand, operator, right operand |
| `Operand` | Typed value source — indicator, feature, field, constant, parameter, with fallback chain |
| `StrategyValidationResult` | Parse output — valid flag, definition, errors, warnings, required columns |

### Runtime entities

| Entity | Description |
|--------|-------------|
| `SignalResult` | Per-bar output — action (buy/sell/hold), direction, stop/target prices, confidence |
| `StrategyMeta` | Static strategy metadata — name, indicators, parameters, data mode |

### Value objects

| Value Object | Description |
|-------------|-------------|
| `StrategySchemaVersion` | Strategy contract version (currently `"2.0"`) |
| `CrossoverState` | Mutable dict tracking `crosses_above`/`crosses_below` previous values |
| `IndicatorCapability` | What an indicator supports — name, period range, data requirements |

---

## Strategy Schema (v2.0)

The strategy schema version is `"2.0"`. This is a **strategy contract version**,
separate from the package semver. Bug-fix releases do not require a schema bump.
Breaking changes to the strategy format require a schema version increment.

### Supported schema features

| Feature | Support |
|---------|---------|
| **Parameters** | int, float, bool, string with type-checking, min/max bounds, defaults, overrides |
| **Indicators** | Fixed-period (sma_20, rsi_14), dynamic-period (sma_37, rsi_21), parameterized via `{{ param }}` |
| **Features** | Rolling max/min, momentum, rate-of-change, z-score, percent-rank, formula-based |
| **Timeframes** | Primary + up to 3 informative timeframes with aliases (e.g., `daily`, `4h`) |
| **Sides** | long, short — each with entry and exit condition trees |
| **Risk** | ATR stop, fixed-percentage stop, risk/reward take-profit, ATR take-profit |
| **Operators** | `<`, `>`, `<=`, `>=`, `==`, `!=`, `between`, `not_between`, `is_true`, `is_false`, `exists`, `missing`, `crosses_above`, `crosses_below` |
| **Groups** | `all`, `any`, `not` — arbitrary nesting depth |
| **Operand sources** | Primary + fallback chain — resolves the first non-None, non-NaN bar value |

### Validation & limits

The parser enforces:

- Unknown indicators → rejected with JSON path
- Unsupported operators → rejected with JSON path
- Parameter overrides outside min/max → rejected
- Max indicators: 8
- Max features: 8
- Max parameters: 12
- Max condition depth: 5
- Warning if no exit rule defined
- Warning if no stop-loss defined

---

## Indicators catalog

The `[pandas]` extra provides `PandasTaIndicatorCalculator`, which computes
all supported indicators on OHLCV DataFrames. Indicators are grouped by
trading theory:

### Momentum & trend

| Indicator | Description | Parameters |
|-----------|-------------|------------|
| `sma_N` | Simple Moving Average | period (2–200) |
| `ema_N` | Exponential Moving Average | period (2–200) |
| `macd` | MACD line (12/26/9) | — |
| `macd_signal` | MACD signal line | — |
| `macd_hist` | MACD histogram | — |
| `rsi_N` | Relative Strength Index | period (2–100) |
| `adx` | Average Directional Index (14) | — |
| `ker` | KAMA Efficiency Ratio (10) | — |
| `kama` | Kaufman Adaptive MA (10) | — |

### Trend classification (compound indicators)

| Indicator | Requires | Output |
|-----------|----------|--------|
| `price_vs_sma20` | sma_20 | AT / ABOVE / BELOW |
| `trend_direction` | sma_20, sma_50, sma_200 | BULLISH / BEARISH / NEUTRAL |
| `trend_strength` | adx | STRONG / MODERATE / WEAK |
| `trend_status` | adx, trend_direction | TRENDING / RANGING / TRANSITION |

### Volatility

| Indicator | Description |
|-----------|-------------|
| `atr` | Average True Range (14) |
| `bb_upper` / `bb_middle` / `bb_lower` | Bollinger Bands (20, 2σ) |
| `vol_buffer_high` / `vol_buffer_low` | ATR-based volatility buffer (±0.1 ATR) |

### Auction Market Theory (AMT)

#### Volume Profile

| Indicator | Description |
|-----------|-------------|
| `vp_poc` | Point of Control (session) |
| `vp_vah` | Value Area High (session) |
| `vp_val` | Value Area Low (session) |
| `rvp_poc_N` | Rolling VP POC (N-bar window) |
| `rvp_vah_N` | Rolling VP VAH |
| `rvp_val_N` | Rolling VP VAL |
| `cvp_poc_Nd` | Composite VP POC (N-day window) |
| `cvp_vah_Nd` | Composite VP VAH |
| `cvp_val_Nd` | Composite VP VAL |
| `vp_poc_Nd` | Parameterized session VP (N days) |

#### Auction state classifiers

| Indicator | Type | Description |
|-----------|------|-------------|
| `inside_value` | bool | Price inside session value area |
| `above_value` | bool | Price above session VAH |
| `below_value` | bool | Price below session VAL |
| `at_poc` | bool | Price at the session POC |
| `near_vah` | bool | Price within 5% of VAH |
| `near_val` | bool | Price within 5% of VAL |
| `distance_to_vah_pct` | float | Percentage distance to VAH |
| `distance_to_val_pct` | float | Percentage distance to VAL |
| `value_area_width_pct` | float | VA width as % of POC |
| `balance_status` | string | BALANCED / IMBALANCED_UP / IMBALANCED_DOWN |

#### AMT rule signals

| Indicator | Type | Description |
|-----------|------|-------------|
| `acceptance_into_value` | bool | Price re-enters VA from outside — AMT Rule 1 |
| `rejection_from_value` | bool | Price touches VA edge and reverses out |
| `value_area_breakout` | bool | Price breaks through VA edge with conviction |
| `excess` | bool | Price spikes far beyond VA (potential exhaustion) |
| `responsive_buying` | bool | Absorption at VAL — aggressive selling met by passive buying |
| `responsive_selling` | bool | Absorption at VAH — aggressive buying met by passive selling |
| `initiative_buying` | bool | Breakout above VAH with follow-through |
| `initiative_selling` | bool | Breakdown below VAL with follow-through |

### Wyckoff Method

| Indicator | Type | Description |
|-----------|------|-------------|
| `wyckoff_phase` | string | ACCUMULATION / MARKUP / DISTRIBUTION / MARKDOWN / NEUTRAL |
| `is_accumulation` | bool | Wyckoff accumulation phase |
| `is_markup` | bool | Wyckoff markup phase |
| `is_distribution` | bool | Wyckoff distribution phase |
| `is_markdown` | bool | Wyckoff markdown phase |
| `is_wyckoff_neutral` | bool | No clear Wyckoff phase |

### Profile shape (Market Profile / Steidlmayer)

| Indicator | Type | Description |
|-----------|------|-------------|
| `profile_shape` | string | NORMAL / P_SHAPE / B_SHAPE / D_SHAPE / NEUTRAL |
| `is_normal_shape` | bool | Bell-shaped — balanced, two-sided trade |
| `is_b_shape` | bool | Heavy bottom — selling accepted, buyers fading |
| `is_p_shape` | bool | Heavy top — buying accepted, sellers fading |
| `is_d_shape` | bool | Thin ends, heavy middle — extreme balance, breakout imminent |
| `is_neutral_shape` | bool | No dominant shape |

### Market Profile (TPO-based)

| Indicator | Description |
|-----------|-------------|
| `mp_poc` | TPO Point of Control |
| `mp_vah` | TPO Value Area High |
| `mp_val` | TPO Value Area Low |

### VWAP bands (Auction Market Theory)

| Indicator | Description |
|-----------|-------------|
| `vwap` | Volume-Weighted Average Price |
| `vwap_upper_1` | VWAP + 1σ (session-scoped) |
| `vwap_lower_1` | VWAP − 1σ |
| `vwap_upper_2` | VWAP + 2σ |
| `vwap_lower_2` | VWAP − 2σ |

### Coil / squeeze detector

| Indicator | Type | Description |
|-----------|------|-------------|
| `is_coil` | bool | Bollinger Bands inside Keltner Channels — compression |
| `coil_duration` | int | Number of consecutive bars in coil |

### Support / resistance

| Indicator | Description |
|-----------|-------------|
| `swing_high_20` | 20-bar rolling high |
| `swing_low_20` | 20-bar rolling low |
| `breakout_level` | Composite resistance (BB upper or swing high) |
| `breakout_signal` | NONE / BREAKOUT_UP / BREAKOUT_DOWN |
| `breakout_quality` | LOW / MEDIUM / HIGH (volume + IBS confirmation) |
| `is_power_zone` | Price within 0.5% of breakout level |

### Initial Balance (Auction Market Theory)

| Indicator | Description |
|-----------|-------------|
| `ib_high` | Initial Balance high (first N bars of session) |
| `ib_low` | Initial Balance low |
| `ib_range` | IB high − IB low |
| `ib_midpoint` | (IB high + IB low) / 2 |

### Proxies (daily-equivalent estimates from intraday bars)

| Indicator | Description |
|-----------|-------------|
| `proxy_ibs` | Internal Bar Strength (close − low) / (high − low) |
| `proxy_rvol` | Relative Volume — volume / SMA(volume, 20) |
| `proxy_parkinson` | Parkinson volatility estimator (daily range) |
| `proxy_garman_klass` | Garman-Klass volatility estimator (OHLC) |
| `proxy_rogers_satchell` | Rogers-Satchell volatility (drift-robust) |
| `proxy_yang_zhang` | Yang-Zhang volatility (overnight-aware, up to 14x efficiency vs close-to-close) |
| `proxy_typical_price` | (H + L + C) / 3 — VWAP proxy |
| `proxy_ohlc4` | (O + H + L + C) / 4 |
| `proxy_atr` | Wilder RMA ATR from OHLC |
| `proxy_vwap` | Typical price as simplified VWAP |
| `proxy_expected_move` | Daily expected move from ATR |
| `proxy_slippage` | Slippage estimate from volume |
| `proxy_iv` | Implied volatility proxy from ATR |

### Dynamic period indicators

Any supported base indicator can be parameterized with an arbitrary period:

```
sma_37    → SMA with period 37
rsi_21    → RSI with period 21
atr_15    → ATR with period 15
ema_100   → EMA with period 100
bb_upper_30 → BB upper with period 30
```

Period ranges are validated against the catalog (e.g., SMA: 2–200, RSI: 2–100).

---

## Statefulness contract

The package has two kinds of components with different state management rules:

| Component | Stateful? | Who owns state? | Rules |
|-----------|-----------|-----------------|-------|
| `TradingStrategy` | **Yes** | The strategy instance | Holds crossover tracking for `crosses_above`/`crosses_below`. Call `on_reset()` before each independent run. |
| `ConditionEvaluator` | **Yes** | Held inside `JsonRuleBasedStrategy` | Crossover state committed per-bar. Never share across strategy instances. |
| `IndicatorCalculator` | **No** | Stateless | Recomputes all columns from a full DataFrame each call. Pass the full bar window, not just the latest bar. |
| `RiskPriceCalculator` | **No** | Stateless | Pure function: RiskSpec + bar + side → (stop, target). |
| `StrategyDefinitionParser` | **No** | Stateless | Pure function: text → StrategyValidationResult. |

### Batch usage (backtesting)

```python
strategy = factory.create(definition)        # one instance per run
strategy.on_reset()                          # clear crossover state
enriched = calculator.calculate(df, indicators)  # enrich all bars at once
for bar in enriched.iter_dicts():            # iterate bars sequentially
    signal = strategy.on_bar(bar, position)  # state accumulates across bars
```

### Incremental usage (live / streaming)

```python
strategy = factory.create(definition)        # one instance per symbol
# NEVER recreate mid-session, NEVER share across symbols
for each closed candle:
    warmup_window.append(candle)
    enriched = calculator.calculate(warmup_window, indicators)  # recompute full window
    latest_bar = enriched.iloc[-1].to_dict()
    signal = strategy.on_bar(latest_bar, position)  # crossover state persists
```

---

## Operators reference

### Comparison operators

| Operator | Description | Example |
|----------|-------------|---------|
| `<` | Less than | `rsi < 30` |
| `>` | Greater than | `close > sma_200` |
| `<=` | Less than or equal | `atr <= 2.0` |
| `>=` | Greater than or equal | `volume >= 1000000` |
| `==` | Equal (within 1e-9 tolerance) | `close == vp_poc` |
| `!=` | Not equal | `trend_direction != NEUTRAL` |

### Range operators

| Operator | Description | Example |
|----------|-------------|---------|
| `between` | Value in [low, high] (inclusive) | `rsi between [30, 70]` |
| `not_between` | Value outside (low, high) | `atr not_between [1, 5]` |

### Boolean operators

| Operator | Description |
|----------|-------------|
| `is_true` | Value is truthy |
| `is_false` | Value is falsy |
| `exists` | Value is not None and not NaN |
| `missing` | Value is None or NaN |

### Crossover operators (stateful — require two consecutive bars)

| Operator | Description |
|----------|-------------|
| `crosses_above` | Left crosses above right (previous value ≤ right, current > right) |
| `crosses_below` | Left crosses below right (previous ≥ right, current < right) |

### Group operators

| Operator | Description |
|----------|-------------|
| `all` | All children must be true |
| `any` | At least one child must be true |
| `not` | Single child — result is negated |

---

## Risk models

### Stop-loss types

| Type | Formula (long) | Formula (short) |
|------|---------------|-----------------|
| `atr` | `close − atr × multiplier` | `close + atr × multiplier` |
| `fixed_pct` | `close × (1 − pct)` | `close × (1 + pct)` |
| `none` | `0.0` | `0.0` |

### Take-profit types

| Type | Formula (long) | Formula (short) |
|------|---------------|-----------------|
| `atr` | `close + atr × multiplier` | `close − atr × multiplier` |
| `fixed_pct` | `close × (1 + pct)` | `close × (1 − pct)` |
| `risk_reward` | `close + |close − stop| × ratio` | `close − |close − stop| × ratio` |
| `none` | `0.0` | `0.0` |

---

## Interfaces (for dependency injection)

All concrete implementations implement domain interfaces (ABCs), enabling
callers to swap implementations without changing orchestration code:

| Interface | Method | Concrete implementation |
|-----------|--------|------------------------|
| `StrategyDefinitionParser` | `parse(text, overrides) → StrategyValidationResult` | Parser (YAML/JSON) |
| `TradingStrategy` | `on_bar(bar, position) → SignalResult` | Rule-based strategy |
| `RiskPriceCalculator` | `calculate(risk, bar, side) → (stop, target)` | JSON risk calculator |
| `IndicatorCalculator` | `calculate(frame, indicators) → frame` | Pandas-TA calculator |
| `IndicatorCapabilityProvider` | `resolve(type, period)`, `supports_concrete(name)` | Indicator catalog |
| `ConditionTreeVisitor` | `visit_group(group)`, `visit_condition(condition)` | Serializer, explainer, column collector |

Orchestration code should depend on these interfaces — never on concrete
implementations. Wire concrete classes in a composition root or factory.

---

## What this package does NOT do

The package is deliberately limited to the runtime subset:

| Concern | Not included — add in your application |
|---------|---------------------------------------|
| Data fetching (exchange APIs, web scrapers) | Build your own fetcher |
| REST API / HTTP servers | Add FastAPI, Flask, or similar |
| SQL repositories / ORM tables | Add SQLAlchemy or your preferred ORM |
| Backtest engine (fills, slippage, position sizing, equity curves) | Implement in your backtester |
| Optimization (grid search, walk-forward) | Implement in your optimizer |
| Job managers / async queues | Add Celery, RQ, or asyncio |
| Live order execution / exchange gateways | Implement in your trading bot |
| Portfolio construction / correlation / allocation | Add your allocation logic |

**Forbidden dependencies:** FastAPI, FastMCP, SQLAlchemy, HTTP clients,
exchange SDKs, or any application-specific packages.

**Allowed dependencies:** stdlib, `typing`, `dataclasses`, optional `numpy`,
optional `pandas`, optional `pandas-ta`, optional `pyyaml`.

---

## Installing without PyPI

You do **not** need to publish this package to PyPI. Consuming applications
can install it directly from a local path:

```bash
# Direct install
pip install /path/to/packages/strategy-runtime

# Editable install (changes to the package are reflected immediately)
pip install -e /path/to/packages/strategy-runtime

# With extras
pip install /path/to/packages/strategy-runtime[pandas,yaml]
```

In a consuming project's `pyproject.toml`:

```toml
[project]
dependencies = [
    "strategy-runtime @ file:///../packages/strategy-runtime",
]
```

Or in `requirements.txt`:

```
strategy-runtime @ file:///path/to/packages/strategy-runtime#egg=strategy-runtime
```

This works across machines as long as the relative path is consistent (e.g.,
both projects live in the same monorepo).

---

## Causal Streaming Enrichment (Jun 2026)

The package now owns **causal enrichment semantics** — the shared contract
between Finbar (backtests) and Finbot (live trading). Both systems consume
the same `CausalMultiTimeframeStreamingEnricher` so enriched rows are
identical in replay and live execution.

### Two enrichment modes

| Mode | Default | Safe For | Use Case |
|------|---------|----------|----------|
| **`live_parity_streaming`** | ✅ | All strategies | Live-tradable results; each row computed from bars available at that bar's close |
| `batch_full_frame` | No | TA-only (sma, rsi, macd) | Research; full-frame batch with VP lookahead for session metrics |

### CausalMultiTimeframeStreamingEnricher

```python
from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (
    CausalMultiTimeframeStreamingEnricher,
)

# One-call enrichment (Finbar backtests, Finbot replay)
frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
    primary_bars=[...],
    informative_bars={"h1": [...]},
    definition=parsed_definition,
    primary_indicators=["vp_poc", "near_val", "atr"],
    informative_indicators={"h1": ["poc_slope_5"]},
    parallel=True,  # informative engines in parallel threads
)

# Live candle processing (Finbot WebSocket)
enricher = CausalMultiTimeframeStreamingEnricher.from_strategy_definition(
    definition, primary_indicators, informative_indicators,
)
enricher.update("h1", h1_bar)              # informative → returns None
latest = enricher.update("primary", bar)   # → CausalEnrichedBar
if latest.is_ready:
    signal = strategy.on_bar(latest.values, position=None)
```

### Streaming performance architecture

The streaming engine (`StreamingIndicatorEngine`) maps each indicator to
an online state class for O(1) or O(window) per-bar cost:

| State Class | Metrics | Per-Bar Cost |
|-------------|---------|:------------:|
| `SmaState`, `EmaState`, `RsiState`, `AtrState`, `VwapState` | sma, ema, rsi, atr, vwap, ibs, rvol, ker, kama | O(1) |
| `IncrementalSessionVpState` | vp_poc, vp_vah, vp_val | O(session_size) |
| `BatchedWindowedState` | near_val, above_value, rejection_from_edge, poc_slope_5, stopping_volume, etc. | O(window) — shared batch compute |
| `RollingVolumeProfileState` | rvp_poc_N, rvp_vah_N, rvp_val_N | O(window) |
| `PrefixRecomputeIndicatorState` | hurst_exponent, market_regime, profile_shape, etc. | O(prefix) |

**Key optimization: `BatchedWindowedState`** replaces N independent
`WindowedIndicatorState` instances with one shared ring buffer. All windowed
metrics are computed in one batch call per bar. VP values from
`IncrementalSessionVpState` are injected via `set_injected_columns()` to
avoid duplicate dependency recompute.

Result: **~80× faster** for the AMT MTF strategy (200→14ms/bar).

### Coverage matrix

Every metric in the unified catalog is classified as `STREAMING_CORRECT` or
`STREAMING_UNSUPPORTED`. The `StreamingCoverageMatrix.load_default()` resource
tracks all 250+ metrics. After the causal parity work (Jun 2026), **zero
metrics are unsupported** — the full catalog is causal-safe.

---

## License

Proprietary. See repository LICENSE.
