# Streaming Indicator Calculator

## User Story
As a live trading runtime author (Finbot), I want to compute strategy
indicators one bar at a time with bounded state, so that per-candle
enrichment cost depends on the number of *new* bars (one) rather than
on the warmup window size, enabling high-cadence, multi-ticker, and
intraday strategies without per-candle cost growing with `n`.

## Context
`PandasTaIndicatorCalculator.calculate(df, indicators)` recomputes
**every** requested indicator over the **full** OHLCV frame on every
call:

- `result = df.copy()` allocates an `O(n × cols)` frame.
- Each handler calls `pandas_ta` over an entire column, producing a
  full-length Series (e.g. `ta.rsi(df["close"], length=7)`), then
  assigns `result[name]`.
- The per-call `cache` dict only de-duplicates *within one* `calculate()`
  call (e.g. `macd_signal` reuses `macd`). It is **fresh on every call**,
  so across candles the whole frame is recomputed from scratch.

The downstream contract makes most of this work redundant:

- Finbot's runtime calls `latest_bar(enriched)` and reads **exactly one**
  row.
- That row (a flat dict of scalars) is passed to
  `JsonRuleBasedStrategy.on_bar(bar, position)`, which evaluates
  conditions against `bar[name]` scalar fields only. The strategy keeps
  crossover state internally; it never reads historical indicator
  columns.

Therefore every candle pays `O(n × Σ indicator-cost)` plus an
`O(n × cols)` frame copy, to keep one scalar per indicator. Finbot's
`_trim_frame` bounds `n = 500`, so the cost is bounded — but it scales
with warmup size and indicator count, not with the number of new bars
(which is one per candle).

Today (minute candles, a dozen indicators) this is tolerable (low
single-digit ms/candle). It becomes the dominant candle-loop cost for:

- intrabar / sub-minute execution
- the multi-ticker portfolio runtime (cost × ticker count)
- large warmup (`sma_200` needs ≥ 200 bars; `max_length = 500`)
- heavy microstructure / profile indicator sets

`BotEventLoop` already logs a warning when candle work exceeds 1 second.

Most core indicators admit an **O(1) per-bar online update**:
SMA (rolling sum), EMA (recursive α), RSI (Wilder smoothing), ATR
(Wilder TR smoothing), MACD (two EMAs + signal EMA), ADX (running
DM+/DM-/TR smoothing), BB (rolling mean + variance → std), KER/KAMA
(rolling), IBS (O(1) from latest bar), VWAP (session cumulative),
rvol (rolling sum). Windowed indicators (session / rolling-window /
composite volume profile, rolling-scalar microstructure proxies) do
not admit a clean online update; they fall back to a bounded-window
recompute (window ≪ n).

**The remaining ~183 indicators** (price-action, SMC, VSA, supply/demand,
microstructure spreads, AMT signals, proxies, Bill Williams, regime)
have no hand-written online form. Rather than crash any strategy that
uses one, they fall back to the same bounded-window recompute —
correct (`O(window)`), just not optimal. This **windowed-default** rule
(03-domain.md) is what makes the streaming engine adoptable without
first hand-writing 183 state classes; hot indicators get promoted to
true streaming state in later slices.

## Scope
This spec lives in the Finbar `finbar_strategy_runtime` package. It adds
a streaming indicator capability and a batch↔streaming parity contract,
**without** changing the existing batch `calculate()` path used by
backtesting, replay, and validation. Finbot-side consumption is a
follow-up spec (out of scope here).

## Non-Goals
- Changing the batch `IndicatorCalculator.calculate()` behaviour or its
  return type — backtest/replay/validation must be unaffected.
- Changing strategy schema, parser, condition evaluator, or crossover
  semantics.
- Rewriting volume-profile / rolling-scalar handlers into true
  streaming form in the first slice. They fall back to bounded-window
  recompute (see ADR-1). True sliding-window VP is a later slice.
- Finbot wiring / adapter / runtime changes (separate spec).
- Removing `pandas_ta` as the batch backend.
