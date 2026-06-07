# Running Backtests

Finbar supports two backtest entry points:

1. **By name** — `run_backtest` for built-in or saved strategies
2. **By JSON** — `backtest_strategy_json` for AI-authored strategies

Both produce the same output format with metrics, trades, equity curve, and
diagnostics.

## Quick start

```python
# 1. Fetch data
fetch_price_history("AAPL", "1d", "yfinance", "2024-01-01", "2024-12-31")

# 2. Get cached bars
bars = get_cached_prices("AAPL", "1d", "2024-01-01", "2024-12-31")

# 3. Apply indicators (synchronous, for small datasets)
apply_indicators(bars, '["sma_20","sma_50","rsi_14"]')

# 4. Run backtest
run_backtest(
  bars, strategy_name="sma_crossover",
  symbol="AAPL", interval="1d",
  initial_cash=10000
)
```

For large datasets, use async indicator jobs:

```python
# Async: compute_indicators → poll → get results
compute_indicators("AAPL", "yfinance", "1d", '["sma_20","rsi_14"]')
# → job_id
get_indicator_job_progress(job_id)
get_indicator_job_results(job_id, page=0)
```

## Execution controls

All backtest and optimization tools accept these parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `leverage` | 1.0 | Leverage multiplier (1.0 = spot) |
| `risk_mode` | `fixed_equity_risk` | Risk sizing: `fixed_equity_risk` or `leverage_scaled_risk` |
| `commission_pct` | 0.0 | Commission per side (decimal) |
| `slippage_pct` | 0.0 | Directional slippage (decimal) |
| `risk_per_trade` | 0.02 | Fraction of portfolio risked per trade |
| `cap_explicit_size` | true | Cap explicit strategy sizes to buying power |
| `reject_oversized_explicit_orders` | false | Reject instead of cap |
| `allow_negative_cash` | false | Allow fills that overdraw cash |
| `market_calendar` | `equity_regular_hours` | `equity_regular_hours` or `crypto_24_7` |
| `borrow_fee_annual_pct` | 0.0 | Annual borrow fee for shorts |
| `margin_mode` | `simplified` | `simplified` or `full` (separate margin tracking) |
| `maintenance_margin_pct` | 0.005 | Maintenance margin fraction (full mode) |
| `enable_funding` | false | Apply per-bar funding payments (full mode) |
| `funding_rate` | 0.0001 | Funding rate per bar (full mode) |

## Multi-timeframe backtests

```python
# For built-in strategies:
merge_and_backtest(
  primary_bars_json, informative_bars_json,
  strategy_name="auction_drive", informative_interval="1d"
)

# For JSON strategies:
backtest_strategy_json(
  definition_json, bars_artifact_id=primary_job_id,
  informative_bars_artifact_ids_json='{"daily":"daily_job_id"}'
)
```

## Output

Every backtest returns:

```json
{
  "total_return": 0.1235,
  "sharpe_ratio": 1.42,
  "max_drawdown": -0.0523,
  "win_rate": 0.625,
  "profit_factor": 2.31,
  "total_trades": 42,
  "trades": [{...}],
  "equity_curve": [{...}],
  "analytics": {
    "rolling_sharpe_60": [null, ..., 1.42],
    "rolling_win_rate_60": [null, ..., 0.60],
    "rolling_drawdown": [0.0, 0.0, -0.03, ...],
    "monthly_returns": {"2024-01": 0.03, ...},
    "yearly_returns": {"2024": 0.15},
    "exposure": [0.0, 0.0, 0.85, ...],
    "trade_distribution": {
      "avg_pnl": 150.5,
      "pnl_percentiles": {"p25": -50, "p50": 120, "p75": 300}
    }
  },
  "trust_diagnostics": {
    "gap_aware_fills": true,
    "net_trade_metrics": true,
    "entry_model": "next_bar_open",
    "exit_model": "next_bar_open",
    "margin_mode": "simplified"
  }
}
```

## Execution model

- **Entry**: Signals at bar close → executed at next bar open
- **Exit**: Signals/stop/target at bar close → executed at next bar open
- **Stops before targets**: When both hit in the same bar, stop takes priority
- **Gap-aware**: Gaps through stops/targets fill at the gapped price
- **Net PnL**: Trade PnL includes entry + exit commissions and borrow costs
- **Annualization**: Calendar-aware factors; crypto uses 365-day year
