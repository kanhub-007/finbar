# Domain Model — Streaming Indicator Calculator

## Overview

Two indicator computation contracts coexist:

- **Batch** (existing, unchanged): `IndicatorCalculator.calculate(df,
  indicators) -> df`. Computes all requested indicators over the full
  frame. Used by backtest, replay, validation, and explanation.
- **Streaming** (new): `StreamingIndicatorCalculator` ingests one bar at
  a time, maintains bounded per-indicator state, and exposes the latest
  computed scalar values. Used by live / intrabar runtimes.

The defining correctness property is **parity**: for the same input
sequence, the streaming engine's latest-row value for each indicator
equals the batch calculator's last-row value within float tolerance
(`atol=1e-12, rtol=1e-9`).

## Entities

| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| `LatestBar` (value object) | `values: dict[str, float]`, `is_ready: bool`, `bars_seen: int` | Immutable snapshot returned by `update()` / `latest()` | No |
| `IndicatorKind` (enum) | `STREAMING`, `WINDOWED`, `UNKNOWN` | Classifies a name for engine dispatch | No |

## Value Objects

| Name | Fields | Used where |
|------|--------|------------|
| `LatestBar` | as above | Streaming engine return type |
| `ParityTolerance` | `atol: float`, `rtol: float` | Parity tests; default `atol=1e-12, rtol=1e-9`, windowed VP uses `rtol=1e-7` |

## Domain Events

None. The streaming engine is a pure computational service with no I/O.

## Interfaces (for DI)

### Existing — `IndicatorCalculator` (unchanged)
```python
class IndicatorCalculator(ABC):
    @abstractmethod
    def calculate(self, df: Any, indicators: list[str]) -> Any: ...
```

### New — `StreamingIndicatorCalculator`
Lives in `domain/interfaces/streaming_indicator_calculator.py`.

```python
class StreamingIndicatorCalculator(ABC):
    """Compute indicators one bar at a time with bounded state.

    The contract is incremental: callers feed closed bars in order and
    read the latest-row scalar values. Per-bar cost for a streaming
    indicator is O(indicator-cost); for a windowed indicator it is
    O(window). Neither depends on the total number of bars seen.
    """

    @abstractmethod
    def update(self, bar: dict) -> LatestBar:
        """Ingest one OHLCV bar; return the latest-row snapshot."""

    @abstractmethod
    def latest(self) -> LatestBar:
        """Return the most recent snapshot without ingesting a bar."""

    @abstractmethod
    def is_ready(self) -> bool:
        """True once at least MIN_BARS bars have been ingested."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all per-indicator state (parity with on_reset)."""
```

### `StreamingIndicatorEngine` (concrete, infrastructure layer)
```python
class StreamingIndicatorEngine:
    """Maps indicator names to per-indicator online state objects.

    Each indicator name resolves (via the existing handler/registry +
    dynamic dispatch) to one of:

      - a :class:`StreamingIndicatorState` (O(1) update), or
      - a :class:`WindowedIndicatorState` (bounded ring buffer +
        recompute over the window only), or
      - an :class:`UnsupportedStreamingState` (raises a clear error at
        construction so a strategy cannot silently fall back).
    """
```

## Streaming state objects

One class per indicator *family*, in `infrastructure/indicators/streaming/`,
each exposing `update(bar: dict) -> float | None` and `reset()`:

| State class | Indicators | Per-bar cost | Algorithm |
|-------------|-----------|--------------|-----------|
| `SmaState` | `sma_N`, `sma_10/20/50/200` | O(1) | running sum + count over a `deque(maxlen=N)` |
| `EmaState` | `ema_12`, `ema_26` | O(1) | `ema = α·x + (1−α)·ema`, seeded with SMA over first `length` (match `pandas_ta`) |
| `RsiState` | `rsi_7`, `rsi_14` | O(1) | Wilder smoothed avg-gain / avg-loss |
| `AtrState` | `atr` | O(1) | Wilder TR smoothing (length=14) |
| `AdxState` | `adx` | O(1) | smoothed +DM/−DM/TR → DI± → DX → ADX |
| `MacdState` | `macd`, `macd_signal`, `macd_hist` | O(1) | one `EmaState(12)`, one `EmaState(26)`, one signal `EmaState(9)`; serves all three outputs |
| `BbState` | `bb_upper/middle/lower` | O(1) | rolling mean + M2 (variance) over `length=20` |
| `KerState`, `KamaState` | `ker`, `kama` | O(1) | rolling change / rolling abs-sum (KER); KAMA recursive |
| `VwapState` | `vwap` | O(1) per bar | session cumulative (PV)/V; resets on session boundary |
| `IbsState` | `ibs` | O(1) | `(C−L)/(H−L)` from the bar itself |
| `RvolState` | `rvol` | O(1) | rolling volume SMA(20) + division |
| `WindowedIndicatorState` | `rvp_*`, `vp_*Nd`, `cvp_*Nd`, rolling-scalar proxies | O(window) | `deque(maxlen=window)` + recompute via existing batch handler on the window slice |

### Shared MACD sub-state
`MacdState` owns the three EMAs and exposes `macd()`, `signal()`,
`hist()`. When a strategy requests only `macd_signal`, the engine still
instantiates one `MacdState` so there is a **single source of truth**
(Scenario 3). This mirrors the batch calculator's per-call `cache`.

### `SUPPORTED_STREAMING_SETS` — the parity-test matrix

The randomised parity test (Scenario 7) parametrises over this exact
list. Each entry is a set of indicators computed together (a strategy's
likely indicator list). Splitting them lets a failure pinpoint the
state class at fault.

```python
# Hand-written STREAMING state classes — tight tolerance (atol=1e-12, rtol=1e-9)
SUPPORTED_STREAMING_SETS = [
    {"sma_20", "sma_50", "sma_200"},     # SmaState (+ dynamic sma_N)
    {"ema_12", "ema_26"},                # EmaState (+ dynamic ema_N)
    {"rsi_7", "rsi_14"},                 # RsiState (+ dynamic rsi_N)
    {"atr"},                             # AtrState (+ dynamic atr_N)
    {"adx"},                             # AdxState
    {"macd", "macd_signal", "macd_hist"},# MacdState (shared sub-state)
    {"bb_upper", "bb_middle", "bb_lower"},# BbState
    {"ker", "kama"},                     # KerState / KamaState
    {"vwap"},                             # VwapState (session-cumulative)
    {"ibs"},                             # IbsState
    {"rvol"},                            # RvolState
]

# Dynamic-period families — one representative each, tight tolerance
SUPPORTED_DYNAMIC_SETS = [
    {"sma_37"}, {"ema_21"}, {"rsi_21"}, {"atr_7"}, {"adx_7"}, {"bb_upper_20"},
]

# VP-prefix WINDOWED — loose tolerance (atol=1e-9, rtol=1e-7)
SUPPORTED_VP_SETS = [
    {"rvp_poc_48"}, {"vp_poc_10d", "vp_vah_10d", "vp_val_10d"},
]

# Windowed-default representatives — loose tolerance. One per handler
# family to prove the fallback is correct without enumerating all 183.
SUPPORTED_WINDOWED_DEFAULT_SETS = [
    {"bearish_fvg"},                    # price-action / SMC
    {"demand_zone_score"},              # supply/demand (volume arg fix)
    {"corwin_schultz_spread"},          # microstructure spread
    {"awesome_oscillator"},             # Bill Williams
    {"proxy_vwap"},                     # proxy (post unify-proxy-dispatch)
    {"poc_rejection"},                  # AMT signal
    {"hurst_exponent"},                 # regime (large min_lookback)
]

ALL_PARITY_SETS = (
    SUPPORTED_STREAMING_SETS
    + SUPPORTED_DYNAMIC_SETS
    + SUPPORTED_VP_SETS
    + SUPPORTED_WINDOWED_DEFAULT_SETS
)
```

**Selection rule for windowed-default reps:** one indicator per handler
family file (price_action, microstructure, supply_demand_zones,
bill_williams, inside_bar/proxies, market_profile_amt, hurst_regime).
This catches a per-family parity break without making the parity suite
run 183 separate jobs. The full 183 are covered structurally: if one
member of a family passes parity, every member using the same
`WindowedIndicatorState` machinery + the same batch handler will too
(the only per-indicator variable is `min_lookback`).

## Indicator classification

A name → kind resolver (`classify_indicator(name) -> IndicatorKind`)
drives construction. Classification has **four tiers**, evaluated in
order:

1. **Hand-listed `STREAMING`** (O(1) online state) — the indicators in
   the state-object table below. These are the only names that get a
   hand-written state class.
2. **Dynamic-period `STREAMING`** — `sma_N`, `ema_N`, `rsi_N`, `atr_N`,
   `adx_N`, `bb_*_N` for any `N` (the dynamic dispatcher parses these).
3. **VP-prefix `WINDOWED`** — `rvp_*`, `vp_*Nd`, `cvp_*Nd`. Explicit
   because their window is parsed from the name (e.g. `vp_poc_10d` →
   window 10).
4. **Windowed-default** — **any other registered handler** falls back to
   `WindowedIndicatorState(maxlen=max(min_lookback, MIN_BARS))`. This is
   the critical rule: it makes ~183 indicators (price-action, SMC, VSA,
   microstructure, AMT, Bill Williams, proxies, …) **computable under
   streaming** instead of crashing construction. Correctness is
   guaranteed by parity (same handler, same window); optimality is not
   (O(window), not O(1)).
5. **`UNKNOWN`** — a name with no registered handler and no matching
   dynamic/VP pattern → raises `UnsupportedStreamingIndicatorError` at
   engine construction. This is the only fail-closed path.

**Why windowed-default exists:** the streaming spec's motivating win is
the ~22 hot indicators on the live candle loop. But a live strategy that
also reads `bearish_fvg` or `corwin_schultz_spread` must still work.
Windowed-default reuses the existing batch handler over a bounded
`deque(maxlen=window)` slice, so every registered indicator is correct
under streaming — slow ones just pay `O(window)` instead of `O(1)`.
Windowed-default is the rule that makes the streaming spec adoptable
without first hand-writing 183 state classes.

**Window source:** `MarketMetricDefinition.min_lookback` (from the
unified metric catalog). For names without a registry entry (legacy
parser indicators), default `max(min_lookback, MIN_BARS)` to
`MIN_BARS=10`. The classifier resolves `min_lookback` via
`UnifiedMetricCatalog.get(name).min_lookback` when present.

## Entity vs ORM separation

N/A — no persistence. All indicator state is in-process and discarded on
`reset()` or GC.

## Resolved decisions (confirmed during spec verification)

1. **VWAP session boundary** — `pandas_ta.vwap` groups by calendar date.
   The streaming engine tracks the last bar's timestamp/date from the
   bar dict; `VwapState` resets when the date changes. If the bar lacks a
   `timestamp` field, treat as one continuous session (document this in
   `VwapState` docstring and add a Scenario 1 "Also test" case).

2. **Windowed VP tolerance** — default `rtol=1e-7, atol=1e-9` for all
   windowed indicators (VP prefixes AND windowed-default). The looser
   tolerance is required because the windowed recompute truncates the
   session bucket grid / uses a finite `deque` slice, so floating-point
   sums differ from the batch full-frame sum at the ~1e-7 level. Pin the
   exact value from the Scenario 8 fixture at implementation time and
   record it in `02-scenarios.md`. Hand-written `STREAMING` indicators
   use the tight `atol=1e-12, rtol=1e-9` (they replicate pandas_ta
   exactly).

3. **Unknown-indicator policy — RESOLVED via windowed-default.** The
   original worry ("a live strategy using an indicator with no streaming
   state fails closed") is answered by tier 4 of the classifier: any
   registered handler without a hand-written state class becomes
   `WINDOWED`, not `UNKNOWN`. `UNKNOWN` (fail-closed) now applies **only**
   to genuinely unknown names — typos, unregistered metrics. No real
   strategy fails to construct because every catalogued metric has a
   handler.

   **Adoptability check (verified 2026-06-16):** of 229 registered
   handlers, ~22 are hand-classified STREAMING, ~24 are VP-prefix
   WINDOWED, and the remaining **183** all have registered handlers and
   therefore fall under windowed-default. Count of indicators that
   would fail-closed under streaming after this rule: **0** (assuming
   every catalogued name is registered, which the construction-time
   `_validate_consistency` check already enforces).

4. **Parity coverage for windowed-default indicators** — the randomised
   parity test (Scenario 7) must include representatives from the 183,
   not just the 22. See `SUPPORTED_STREAMING_SETS` definition below.
