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

### Liquidation boundary (leveraged entries)

When `leverage > 1.0`, the engine ALSO rejects any entry whose protective
stop is on or beyond the **liquidation price**. This is a separate, often
more restrictive check that prevents strategies from requesting stops that
the exchange would never let you reach.

The liquidation price uses an isolated-margin approximation:

| Direction | Liquidation price |
|-----------|-------------------|
| Long  | `entry × (1 − 1/leverage + maintenance_margin_pct)` |
| Short | `entry × (1 + 1/leverage − maintenance_margin_pct)` |

For the entry to be valid, the stop must sit **inside** the liquidation
boundary (above it for longs, below it for shorts):

```
long : stop_price > liquidation_price
short: stop_price < liquidation_price
```

If the stop is outside the boundary, the entry is rejected with a log line
like:

```
[ENTRY-SKIP] 2026-06-12 | LONG | price=1675.00 stop=1618.00
               beyond liquidation=1616.38 (L=25x)
```

No trade is opened and the bar is skipped.

### Maximum leverage is bounded by stop distance

Because of the liquidation check, a strategy with a wide stop can run at
high leverage, while a tight stop caps the usable leverage. The ceiling is:

```
long :  1 / leverage > stop_pct + maintenance_margin_pct
        where stop_pct = (entry - stop) / entry
```

Equivalently: `max_leverage ≈ 1 / (stop_pct + maintenance_margin_pct)`.

Worked example (ETH 1h, ATR=16.7, `atr_stop_mult=3.5`, `maintenance_margin_pct=0.005`):

```
stop_distance = 16.7 × 3.5 = 58.5   (on a $1,675 entry)
stop_pct      = 58.5 / 1675  = 3.49%
max_leverage  = 1 / (0.0349 + 0.005) ≈ 25.1x
```

So a 3.5×ATR stop on this ETH bar permits up to ~25x leverage. At 26x the
entries would be rejected. Widening the stop (larger `atr_stop_mult`) raises
the ceiling; tightening it lowers the ceiling.

**If a strategy has no stop** (`stop_loss: {type: none}`), the liquidation
check is skipped entirely — any leverage is allowed, but the only protection
is the take-profit or signal exit. One gap and you are liquidated at the
exchange's price, not yours. Use this mode with care.

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

Explicit-size behavior is controlled by execution config:

- `cap_explicit_size=true` (default): cap oversized explicit orders.
- `reject_oversized_explicit_orders=true`: reject oversized explicit orders.
- `allow_negative_cash=true`: allow advanced simulations that overdraw cash.

### Risk-based sizing (engine default)

When no explicit size is given and a stop price is set:

```
size = (portfolio_value * risk_per_trade) / |fill_price - stop_price|
```

Sizing uses the **actual next-open fill price**, including entry slippage, not
the signal-bar open.

⚠️ **`risk_per_trade` is a DECIMAL FRACTION, not a percent.** The default is
`0.02` (= 2%). Passing `risk_per_trade=5` means a **500% risk budget**, not
5%. Use `0.05` for 5%, `0.10` for 10%. This is the single most common
configuration mistake and is called out in every MCP tool's parameter
description.

`risk_mode` controls how the budget interacts with leverage:

| `risk_mode` | Behaviour |
|-------------|-----------|
| `fixed_equity_risk` (default) | Risk budget is a flat fraction of equity. Leverage expands buying power but does NOT multiply the risk budget. |
| `leverage_scaled_risk` | Multiplies the risk budget by leverage (aggressive; amplifies both wins and stop-loss impact). |

**Important**: the risk-based size is **capped** by the affordability rule
below before the order fills. When the cap binds, the *intended* risk per
trade is not the risk actually taken — see the next section.

### Affordability cap (buying-power limit)

Every order — risk-based or explicit — is capped to the position the account
can actually pay for. This is the last gate before a fill and is what keeps
backtests honest under leverage.

```
max_affordable_size = (cash × leverage) / (fill_price × (1 + commission_pct))
filled_size         = min(requested_size, max_affordable_size)
```

Notes:

- **Buying power** = `cash × leverage` (so 3x leverage on $10,000 = $30,000
  of purchasing power, regardless of what `risk_per_trade` requests).
- `allow_negative_cash=true` disables the cap entirely — intended only for
  advanced what-if simulations.
- `cap_explicit_size=true` (default) applies the cap to strategy-supplied
  explicit sizes too. `reject_oversized_explicit_orders=true` rejects the
  order instead of silently capping it.

When the cap binds, the result diagnostics include an `order_resized` /
`affordability_cap` entry recording the requested vs filled size, e.g.:

```json
{
  "severity": "order_resized",
  "code": "affordability_cap",
  "message": "Requested size 855.04 capped to 12.97.",
  "metadata": {"requested_size": 855.04, "filled_size": 12.97}
}
```

**Why this matters for interpreting results**: when the risk-based size is
larger than the affordability cap, every position is effectively maxed out
at 100% of buying power. The `risk_per_trade` parameter stops controlling
risk — leverage and stop distance do. Effective risk per trade becomes
`(stop_distance / entry_price) × leverage × equity`. Always inspect the
`diagnostics` array if you see surprisingly uniform position sizes.

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

## Short borrow cost

When enabled via `borrow_fee_annual_pct`, short positions accrue a
simplified borrow cost based on the entry notional and days held:

```
borrow_cost = entry_notional * borrow_fee_annual_pct * (days_held / 365)
```

The borrow cost is deducted from cash at exit and included in the trade's
net PnL. Long positions are never charged borrow fees. The cost is tracked
cumulatively as `total_borrow_cost` in the result output.

### Margin mode

The engine supports two margin accounting modes:

- `simplified` (default): short proceeds add to cash at entry. Borrow
  cost is applied at exit. Leveraged positions use a liquidation-price
  model derived from the multiplier.
- `full` (future): full margin accounting with initial/maintenance margin
  tracking and funding-rate integration.

The simplified model is documented as a deliberate approximation. It is
suitable for strategy comparison but may understate costs for extended
hold periods or highly leveraged positions.

## Annualization

Periodic returns are annualized using interval- and calendar-aware factors.
The default market calendar is `equity_regular_hours`:

| Interval | Equity periods per year |
|----------|-------------------------|
| `1d` | 252 |
| `1w` | 52 |
| `1h` | 1,638 (252 × 6.5) |
| `30min` | 3,276 (252 × 13) |
| `5min` | 19,656 (252 × 78) |

For continuously traded crypto, pass `market_calendar="crypto_24_7"`:

| Interval | Crypto periods per year |
|----------|-------------------------|
| `1d` | 365 |
| `1w` | 365 / 7 |
| `1h` | 8,760 (365 × 24) |
| `30min` | 17,520 (365 × 24 × 2) |
| `5min` | 105,120 (365 × 24 × 12) |

If the interval is unknown or omitted, results include an
`annualization_warning` describing the fallback assumption.

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
reading engine source code. Order capping/rejection and other execution issues
are emitted as structured diagnostics with `severity`, `code`, `date`, and
`message` fields.

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

- Short positions use a simplified borrow-cost model (`borrow_fee_annual_pct`) rather than dynamic margin/financing. Long positions never pay borrow.
- The `simplified` margin mode uses an isolated-margin approximation. `full` mode tracks initial and maintenance margin explicitly but is less battle-tested.
- Same-bar signal exit and entry: if a strategy exits and immediately enters on the same bar close, both are deferred to the same next open. The exit fills first (because `_execute_pending` processes exits before entries), then the entry fills. This is intentional — you cannot enter while already in a position.
- Market-on-close exit timing is not yet supported (signal exits always defer).
- Annualization factors assume equity hours. Crypto or 24/7 instruments need different factors.
- The affordability cap does not model partial fills or order-book depth — it assumes the full capped size fills at the next bar's open.
