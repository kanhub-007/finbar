# Running Backtests

Finbar supports two backtest entry points:

1. **By name** — `run_backtest` for built-in or saved strategies (small data)
2. **By JSON/YAML** — `backtest_strategy_definition` for AI-authored strategies (preferred).
   YAML is recommended for AI agents — no quote escaping, native indentation.

Both produce the same output format with metrics, trades, equity curve, and
diagnostics.

## Preferred workflow (artifact-based, efficient)

For AI agents with limited context — no large JSON payloads in chat:

```python
# 1. Fetch recent data (always pass start_date)
fetch_price_history("AAPL", "1d", "yfinance", start_date="2024-01-01")

# 2. Compute indicators server-side, limit date range
compute_indicators("AAPL", "yfinance", "1d",
    '["sma_20","sma_50","rsi_14"]', start_date="2024-01-01")
# → job_id

# 3. Poll for completion
get_indicator_job_progress(job_id)

# 4. Get artifact ID → backtest with artifact ID (no bars in context)
backtest_strategy_definition(
  definition_json, bars_artifact_id=job_id,
  symbol="AAPL", interval="1d"
)
→ compact summary + result_id
```

Or use the one-call pipeline:

```python
run_strategy_pipeline(definition_json, "AAPL",
  start_date="2024-01-01")
→ validate → compute indicators → backtest → compact summary
```

## Small-data workflow (legacy, quick experiments)

For small datasets (<500 bars) where inline JSON is acceptable:

```python
# 1. Get recent bars
bars = get_cached_prices("AAPL", tail=100)

# 2. Apply indicators in-memory
enriched = apply_indicators(bars, '["sma_20","rsi_14"]')

# 3. Run backtest
run_backtest(enriched, strategy_name="sma_crossover",
  symbol="AAPL", interval="1d")
```

**Warning:** For large datasets, always prefer the artifact workflow above.
The inline JSON approach can exhaust agent context.

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

For strategies that need intraday entries plus daily trend context:

```python
# 1. Compute indicators for primary + informative timeframes
compute_indicators("AAPL", "yfinance", "1h",
  '["sma_20","rsi_14"]', start_date="2024-01-01")
# → primary_job_id

compute_indicators("AAPL", "yfinance", "1d",
  '["sma_50","sma_200"]', start_date="2024-01-01",
  timeframe_alias="daily")
# → daily_job_id

# 2. Backtest with both artifact IDs
backtest_strategy_definition(
  definition_json,
  bars_artifact_id=primary_job_id,
  informative_bars_artifact_ids_json='{"daily":"daily_job_id"}',
  symbol="AAPL", interval="1h"
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
