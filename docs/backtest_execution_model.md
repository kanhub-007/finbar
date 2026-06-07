# Backtest Execution Model

> Documents the mechanical assumptions behind Finbar backtest fills, timings,
> and reporting. Every trade, PnL, and metric depends on these rules.

## Signal generation

A `TradingStrategy.on_bar(bar, position)` is called once per bar at the bar's
**close**. The strategy sees the entire bar including close, high, low, and all
indicator values. This is the standard "evaluate at close" model.

## Entry execution

All strategy-generated entry signals (`action = "buy"` / `"sell"`, `direction =
"long"` / `"short"`) are deferred by one bar. The signal is stored as a
`PendingEntry` and executed at the **next bar's open**.

| Signal bar | Fill bar | Fill price |
|-----------|----------|------------|
| Bar N close | Bar N+1 open | Bar N+1 `open` |

## Exit execution

Strategy-generated exit signals (`direction = "exit"`) follow the same
deferred model. The signal is stored as a `PendingExit` and executed at the
**next bar's open**.

| Signal bar | Fill bar | Fill price |
|-----------|----------|------------|
| Bar N close | Bar N+1 open | Bar N+1 `open` |

The exit reason is recorded as `signal_exit_next_open`.

## Stop-loss and take-profit execution

Stop-loss and take-profit orders are **active intrabar**, not deferred. They
are checked on every bar using a gap-aware model.

### Long positions

- If `open <= stop_price`, fill at `open` (reason `stop_loss_gap`).
- Else if `low <= stop_price`, fill at `stop_price` (reason `stop_loss`).
- If `open >= target_price`, fill at `open` (reason `take_profit_gap`).
- Else if `high >= target_price`, fill at `target_price` (reason `take_profit`).

If both stop and target are hit in the same bar, **stop-loss takes priority** because it is the protective order. Gap conditions are checked first because the open already establishes what is reachable.

### Short positions

- If `open >= stop_price`, fill at `open` (reason `stop_loss_gap`).
- Else if `high >= stop_price`, fill at `stop_price` (reason `stop_loss`).
- If `open <= target_price`, fill at `open` (reason `take_profit_gap`).
- Else if `low <= target_price`, fill at `target_price` (reason `take_profit`).

## Protective stop validation

When a pending entry is executed, the engine checks that the stop price is
still valid relative to the fill:

- **Long**: `stop_price < fill_price`. If not, the stop cannot protect the
  position. The engine discards the entry with reason `ENTRY-SKIP`.
- **Short**: `stop_price > fill_price`. Same logic.

If no stop is set (`stop_price = 0`), no validation is needed.

## End-of-run liquidation

Any open position at the end of the backtest is **liquidated at the final
bar's close** with reason `end_of_backtest`. This ensures:

- Total trades reflect all position activity.
- Trade `pnl` is net of entry and exit commissions.
- Final equity reconciles with `initial_cash + sum(net_trade_pnl)` for
  liquidated backtests.
- Open positions do not silently inflate returns.

## Position sizing

### Explicit size

If the strategy provides `position_size > 0`, the engine treats that value as
the requested size. The filled size is still capped by available buying power
using the effective slipped fill price plus entry commission. When a requested
size is capped, the result diagnostics include an `affordability_cap` entry.

### Risk-based sizing (engine default)

When no explicit size is given and a stop price is set:

```
size = (portfolio_value * risk_per_trade) / |fill_price - stop_price|
```

Sizing uses the **actual next-open fill price**, including entry slippage, not
the signal-bar open. `risk_per_trade` is fixed-equity risk by default: leverage
expands buying power, but does not multiply the stop-loss risk budget.

### Fallback

If no stop is set, the engine uses 100 shares.

## Multi-timeframe merging

Informative bars are aligned with primary bars using **no-lookahead as-of
merging**. An informative bar becomes available only after its interval has
completed:

| Informative interval | Completion offset | Example |
|---------------------|------------------|---------|
| `5min` | +5 minutes | `10:00` bar available from `10:05` |
| `30min` | +30 minutes | `10:00` bar available from `10:30` |
| `1h` | +1 hour | `10:00` bar available from `11:00` |
| `1d` | +1 day | `2024-01-02` bar available from `2024-01-03 00:00` |
| `1w` | +1 week | Monday bar available from next Monday |

This means intraday bars on a given date **cannot** read same-day daily
indicators. They see the previous completed daily bar's values.

## Transaction costs

### Commission

Applied as a percentage of trade gross value per side. Deducted from cash:

- Entry: `cash -= cost + commission`
- Exit (long): `cash += proceeds - commission`
- Exit (short): `cash -= cost + commission`

Closed trades record both `gross_pnl` and `net_pnl`. The canonical trade
`pnl`, win/loss counts, win rate, and profit factor all use net PnL.

### Slippage

Applied directionally to fill prices:

| Direction | Side | Fill price |
|----------|------|------------|
| Long | Entry | `price * (1 + slippage_pct)` |
| Long | Exit | `price * (1 - slippage_pct)` |
| Short | Entry | `price * (1 - slippage_pct)` |
| Short | Exit | `price * (1 + slippage_pct)` |

Costs are tracked cumulatively as `total_commission` and `total_slippage`.
`total_slippage` includes both entry and exit slippage impact. Both defaults
are zero.

## Annualization

Periodic returns are annualized using interval-aware factors:

| Interval | Periods per year |
|----------|-----------------|
| `1d` | 252 |
| `1w` | 52 |
| `1h` | 1,638 (252 × 6.5) |
| `30min` | 3,276 (252 × 13) |
| `5min` | 19,656 (252 × 78) |

These assume standard equity market hours (6.5 hours/day, 252 days/year).
Crypto markets with 24/7 trading would need different factors.

## Warmup validation

Before the backtest runs, the engine checks that all strategy-required
indicator and feature columns are eventually valid:

1. The first bar where all required columns are non-NaN is the **first
   tradable bar**.
2. Warmup bars before this point are counted and reported.
3. If required columns are never all valid, or become missing again after the
   first tradable bar, JSON strategy backtests are rejected before execution
   with structured validation errors.

## Diagnostics

Every backtest result includes a `trust_diagnostics` section documenting the
active execution model. This makes it possible to audit result quality without
reading engine source code.

## Summary table

| What | When | Price |
|------|------|-------|
| Entry signal | Bar N close | — |
| Entry fill | Bar N+1 open | Bar N+1 `open` |
| Exit signal | Bar N close | — |
| Exit fill | Bar N+1 open | Bar N+1 `open` |
| Stop-loss | Intrabar, any bar | Gap-aware (see above) |
| Take-profit | Intrabar, any bar | Gap-aware (see above) |
| Final liquidation | Last bar close | Last bar `close` |

## Known limitations

- Short positions have no margin/borrow-cost model.
- Same-bar signal exit and entry: if a strategy exits and immediately enters on the same bar close, both are deferred to the same next open. The exit fills first (because `_execute_pending` processes exits before entries), then the entry fills. This is intentional — you cannot enter while already in a position.
- Market-on-close exit timing is not yet supported (signal exits always defer).
- Annualization factors assume equity hours. Crypto or 24/7 instruments need different factors.
