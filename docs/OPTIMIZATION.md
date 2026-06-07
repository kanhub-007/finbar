# Optimization & Walk-Forward

Two forms of parameter optimization are available:

1. **Grid/Random search** — `start_optimization_job` — tests all combinations
   on the full history, returns ranked results.
2. **Walk-forward** — `start_walk_forward_job` — splits data into train/test
   folds, grid-searches each fold, validates out-of-sample.

## Grid search

```python
# After computing indicators:
compute_indicators("AAPL", "yfinance", "1d",
  '["sma_20","sma_50","rsi_14","atr"]')
# → primary_job_id

# Start grid search:
start_optimization_job(
  definition_json='{...strategy...}',
  bars_artifact_id=primary_job_id,
  param_ranges_json='{
    "fast_period": {"min": 5, "max": 30, "step": 5},
    "slow_period": {"min": 20, "max": 100, "step": 10},
    "stop_atr": {"min": 1.0, "max": 4.0, "step": 0.5}
  }',
  metric="sharpe_ratio"
)
# → {"job_id": "...", "status": "queued"}

# Poll:
get_optimization_job_progress(job_id)

# Retrieve:
get_optimization_job_results(job_id)
# → ranked list of {rank, params, sharpe_ratio, total_return, ...}
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `search_method` | `grid` | `grid` (min/max/step) or `random` (min/max/random_count) |
| `metric` | `sharpe_ratio` | `sharpe_ratio`, `sortino_ratio`, `total_return`, `profit_factor`, `win_rate`, `calmar_ratio` |
| `random_count` | 20 | Number of random samples (random mode) |
| Max combinations | 100 | Hard limit across both modes |

### Multi-timeframe optimization

Set `informative_bars_artifact_ids_json='{"daily":"daily_job_id"}'`.

## Walk-forward validation

Splits data into train/test folds. For each fold, runs a grid search on the
training window, then tests the best parameters out-of-sample on the test
window.

```python
start_walk_forward_job(
  definition_json='{...strategy...}',
  bars_artifact_id=primary_job_id,
  param_ranges_json='{
    "fast_period": {"min": 5, "max": 30, "step": 5}
  }',
  folds=5,
  train_ratio=0.7,
  anchor="rolling",
  metric="sharpe_ratio"
)
# → {"job_id": "...", "status": "queued"}
```

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `folds` | 5 | Number of train/test splits |
| `train_ratio` | 0.7 | Fraction per fold for training |
| `anchor` | `rolling` | `rolling` (slides forward) or `anchored` (expands from start) |
| `min_train_bars` | 20 | Minimum bars for training window |
| `min_test_bars` | 5 | Minimum bars for test window |

### Output diagnostics

```json
{
  "total_return": 0.09,
  "sharpe_ratio": 0.85,
  "max_drawdown": -0.12,
  "is_oos_correlation": -0.12,
  "stability": 0.78,
  "avg_rank_correlation": 0.85,
  "folds": [
    {
      "fold_index": 0,
      "train_start": "2024-01-02",
      "test_start": "2024-04-15",
      "oos_sharpe": 0.72,
      "best_params": {"fast_period": 10, "stop_atr": 2.0},
      "param_sensitivity": {"fast_period": 0.65, "stop_atr": 0.35}
    }
  ]
}
```

### Diagnostics explained

| Metric | Range | Meaning |
|--------|-------|---------|
| `is_oos_correlation` | -1.0 … +1.0 | Correlation between IS and OOS Sharpe. Near zero or negative = potential overfitting |
| `stability` | 0.0 … 1.0 | Fraction of best params within 20% of average. 1.0 = fully stable |
| `avg_rank_correlation` | -1.0 … +1.0 | Spearman correlation of parameter importance rankings across folds. 1.0 = params rank consistently important across time |

When `is_oos_correlation` is negative and `stability` is low, the strategy is
likely curve-fit — it performs well in-sample but the optimal parameters change
every fold.

## Job management

All optimization jobs use the same poll/retrieve/cancel pattern:

| Tool | Purpose |
|------|---------|
| `get_optimization_job_progress(job_id)` | Status, combinations done/total, progress % |
| `get_optimization_job_results(job_id)` | Ranked results + (for walk-forward) walk_forward_result block |
| `cancel_optimization_job(job_id)` | Cancel running job |
