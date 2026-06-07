# Finbar MCP Context Optimization Plan

## Purpose

Optimize Finbar's MCP interface for AI agents by reducing large JSON dumps while preserving full-fidelity data. The goal is **not** to discard or truncate data internally. The goal is to store large data server-side and expose it through summaries, IDs, pagination, filtering, and explicit detail-fetch tools.

## Implementation Status

### Completed in Phase 1 Slice

- Fixed artifact TTL cleanup to honor `ttl_hours`.
- Stopped in-memory indicator job cleanup from deleting persisted artifacts.
- Added durable artifact metadata with retention policy in responses.
- Added artifact application DTOs and use cases.
- Added MCP tools:
  - `list_artifacts`
  - `describe_artifact`
  - `query_artifact_bars`
  - `delete_artifact`
- Updated the MCP usage guide to prefer artifact discovery and selective bar queries.
- Added persistence/query/retention tests.

### Completed in Phase 2 Slice

- Added server-side in-memory backtest result store.
- Added compact backtest response envelopes with `result_id`.
- Updated `run_backtest`, `merge_and_backtest`, and `backtest_strategy_json` to return summary responses by default while retaining full results server-side.
- Added MCP tools:
  - `list_backtest_results`
  - `get_backtest_summary`
  - `get_backtest_trades`
  - `get_backtest_equity`
- Added paginated/sortable trade access.
- Added downsampled equity access modes: `none`, `daily`, `weekly`, `drawdown_events`, `page`, `full`.
- Updated the MCP usage guide to document compact result workflows.
- Added compact result access tests.

### Completed in Phase 3 Slice

- Added `compute_strategy_indicators` — validates a strategy JSON and starts indicator jobs across all required timeframes in one call.
- Added `run_strategy_pipeline` — one-call orchestration: validate → check price cache → compute indicators → await jobs → backtest → compact summary.
- Updated the MCP usage guide to prefer orchestrated workflows.

### Remaining

- Query-optimized artifact storage beyond JSON blobs.
- Optional persistent backtest result storage beyond in-memory cache.

## Core Principle

> Large data should be stored, discoverable, paginated, and filterable — not dumped into chat and not silently discarded.

AI agents should receive compact summaries by default, plus stable artifact/result IDs that allow precise follow-up access.

---

## Current Problem

The current context-heavy workflow is:

```text
get_cached_prices()
  → returns bars as inline JSON
apply_indicators(bars_json=...)
  → returns enriched bars as inline JSON
run_backtest(bars_json=...)
  → returns full metrics + full trades[] + full equity_curve[] + analytics
```

For a 5-minute BTC scalp strategy over a long window, this can create enormous payloads:

| Payload | Approximate Size |
|---------|------------------|
| Raw 5min OHLCV bars | tens of MB |
| Enriched bars with indicators | potentially 100MB+ |
| Full per-bar equity curve | many MB |
| Full scalp trade list | hundreds of KB to multiple MB |
| Analytics | smaller, but still unnecessary by default |

This causes agent context exhaustion and makes multi-step workflows fragile.

---

## What the Original Plan Covered Well

The first plan correctly identified the largest size problems:

1. Inline bar JSON between tools.
2. Full equity curve returned by default.
3. Full trade list returned by default.
4. Analytics returned eagerly.
5. Lack of result IDs / backtest result caching.
6. Need for compact inline serialization when inline bars are unavoidable.

The second-pass review adds the missing requirements around agent UX and retention safety.

---

## Critical Safety Finding: Artifact Retention

Artifact IDs are central to efficient agent workflows, so their retention must be reliable and explicit.

Current risks found during review:

1. Indicator artifacts are persisted to SQLite, but the in-memory manager can delete persisted artifacts when terminal jobs expire.
2. `SqlIndicatorArtifactRepository.cleanup_expired(ttl_hours=24)` calculates cutoff as `now`, not `now - ttl_hours`, so if invoked it may delete more artifacts than intended.

### Required Retention Model

Separate three lifecycles:

| Data Type | Purpose | Retention |
|-----------|---------|-----------|
| Raw price cache | Source-of-truth OHLCV | Durable until explicitly deleted |
| Derived artifacts | Enriched bars, features, merged frames | Durable by default; explicit TTL optional |
| In-memory hot cache | Fast DataFrame/pickle access | Ephemeral; safe to evict |

Every artifact response should expose retention metadata:

```json
{
  "artifact_id": "...",
  "created_at": "...",
  "expires_at": null,
  "retention_policy": "durable_until_deleted"
}
```

---

## Target Agent UX: Progressive Disclosure

Large-output tools should default to summary responses and support deeper access on demand.

```text
summary → sample → page → full export
```

### Recommended `detail_level` Values

| detail_level | Returned Data | Use Case |
|--------------|---------------|----------|
| `summary` | Metrics, counts, warnings, IDs | Default for AI agents |
| `sample` | Summary + small representative examples | Quick inspection |
| `page` | One explicit page of rows/trades/equity | Investigation |
| `full` | Full payload only when explicitly requested | Human export/debug |

Default should be `summary`, not `full`.

---

## Standard Response Envelope

Every expensive operation should return a consistent envelope:

```json
{
  "status": "completed",
  "summary": {},
  "ids": {
    "artifact_id": "ind_abc",
    "result_id": "bt_xyz"
  },
  "counts": {
    "bars": 200000,
    "trades": 5234,
    "equity_points": 200000
  },
  "returned": {
    "bars": 0,
    "trades": 0,
    "equity_points": 0
  },
  "access": {
    "bars": "query_artifact_bars(artifact_id, ...)",
    "trades": "get_backtest_trades(result_id, ...)",
    "equity": "get_backtest_equity(result_id, ...)"
  },
  "warnings": [],
  "error": null
}
```

This tells the agent:

1. What happened.
2. What data exists.
3. What was returned.
4. How to fetch more detail.

---

## Required Tool Additions

### Artifact Discovery and Access Tools

#### `list_artifacts`

Allows the agent to discover existing enriched datasets and avoid recomputation.

Returns metadata only:

```json
{
  "artifacts": [
    {
      "artifact_id": "ind_abc",
      "symbol": "BTC-USD",
      "source": "yfinance",
      "interval": "5min",
      "start_date": "2026-01-01",
      "end_date": "2026-06-01",
      "bar_count": 42000,
      "columns": ["open", "high", "low", "close", "volume", "sma_5", "sma_20"],
      "indicators_applied": ["sma_5", "sma_20", "rsi_14"],
      "timeframe_alias": "primary",
      "created_at": "...",
      "expires_at": null
    }
  ]
}
```

#### `describe_artifact`

Returns metadata, schema, date range, columns, null counts, indicator list, feature list, and data-quality diagnostics without returning bars.

#### `query_artifact_bars`

Paginated, date-filtered, column-filtered artifact access:

```text
query_artifact_bars(
  artifact_id="ind_abc",
  columns_json='["timestamp", "close", "sma_20", "rsi_14"]',
  start_date="2026-03-01",
  end_date="2026-03-07",
  page=0,
  page_size=200
)
```

#### `delete_artifact`

Explicit user-controlled cleanup. Durable artifacts should not disappear silently.

---

### Backtest Result Discovery and Access Tools

#### `list_backtest_results`

Lists prior backtests by symbol, strategy, date range, interval, and key metrics.

#### `get_backtest_summary`

Returns only metrics, warnings, diagnostics, and pointers to detail access.

#### `get_backtest_trades`

Paginated and sortable trade access:

```text
get_backtest_trades(
  result_id="bt_xyz",
  page=0,
  page_size=50,
  sort_by="net_pnl",
  sort_dir="asc"
)
```

#### `get_backtest_equity`

Downsampled or paginated equity access:

```text
get_backtest_equity(result_id="bt_xyz", mode="daily")
get_backtest_equity(result_id="bt_xyz", mode="weekly")
get_backtest_equity(result_id="bt_xyz", mode="drawdown_events")
get_backtest_equity(result_id="bt_xyz", mode="page", page=0, page_size=500)
```

---

## Changes to Existing Tools

### 1. Add Artifact IDs to All Bar-Consuming Tools

Already supported partially by `backtest_strategy_json`.

Add artifact support to:

- `run_backtest`
- `apply_indicators`
- `merge_and_backtest`
- any portfolio/backtest tools currently requiring inline bars

This avoids passing OHLCV/enriched bars through the chat context.

### 2. Add `detail_level` to Backtest Tools

Recommended default:

```text
detail_level="summary"
```

Optional values:

```text
summary | sample | page | full
```

### 3. Add Equity Modes

Backtest responses should not include full per-bar equity by default.

Supported modes:

```text
none | daily | weekly | drawdown_events | page | full
```

### 4. Add Trade Pagination

Backtest responses should return trade counts and summary stats by default, not every trade.

Default response should include:

- trade count
- win/loss count
- win rate
- average PnL
- average duration
- top 5 winners
- top 5 losers
- access pointer for paginated full trades

### 5. Make Analytics Optional

Do not compute/return full analytics unless requested.

Add:

```text
include_analytics=false
```

or a separate analytics retrieval tool.

---

## Recommended Agent Workflow

### Avoid as Default

```text
get_cached_prices → apply_indicators → run_backtest
```

This should be considered legacy/small-data mode.

### Preferred Artifact Workflow

```text
validate_strategy_json
  → compute_indicators per timeframe
  → backtest_strategy_json using bars_artifact_id and informative artifact IDs
  → get_backtest_trades only if needed
  → get_backtest_equity only if needed
```

### Ideal One-Call Agent Workflow

Add a high-level orchestration tool:

```text
run_strategy_pipeline(
  definition_json,
  symbol,
  source,
  start_date,
  end_date,
  detail_level="summary"
)
```

This tool should:

1. Validate the strategy.
2. Determine required indicators per timeframe.
3. Check whether raw price cache exists.
4. Return precise missing-data instructions if cache is missing.
5. Reuse existing artifacts when possible.
6. Compute missing artifacts when needed.
7. Run the backtest.
8. Store the full result server-side.
9. Return a compact summary plus artifact/result IDs.

---

## Storage Design

Current artifact persistence stores all bars as one SQLite `Text` JSON blob. This works, but it is inefficient for slicing, pagination, and column selection.

### Short-Term Storage Improvements

Keep the JSON blob initially, but add metadata fields:

- `start_date`
- `end_date`
- `columns_json`
- `row_count`
- `null_counts_json`
- `content_hash`
- `created_at`
- `expires_at`
- `retention_policy`

### Medium-Term Storage Improvements

Use a more query-friendly artifact format:

1. SQLite row-oriented artifact bars, or
2. Parquet files for fast date filtering and column selection.

Clean architecture approach:

- Define `ArtifactRepository` interface in `core/domain/interfaces/`.
- Implement `SqlArtifactRepository` or `ParquetArtifactRepository` in `infrastructure/`.
- Keep MCP tools in `presentation/` depending on application use cases, not infrastructure directly.

---

## Implementation Roadmap

### Phase 1 — Safe Artifact Foundation

1. Fix artifact TTL cleanup bug.
2. Stop deleting persisted artifacts during in-memory cleanup unless explicitly configured.
3. Add artifact metadata: columns, date range, content hash, created time, expiry.
4. Add artifact discovery/access tools:
   - `list_artifacts`
   - `describe_artifact`
   - `query_artifact_bars`
   - `delete_artifact`

### Phase 2 — Compact Backtest Results

1. Add `detail_level="summary"` default.
2. Store full backtest result server-side and return `result_id`.
3. Add:
   - `get_backtest_summary`
   - `get_backtest_trades`
   - `get_backtest_equity`
   - `list_backtest_results`
4. Add equity modes:
   - `none`
   - `daily`
   - `weekly`
   - `drawdown_events`
   - `page`
   - `full`

### Phase 3 — Agent Orchestration

1. Add `compute_strategy_indicators` to compute required indicators from strategy validation automatically.
2. Add `run_strategy_pipeline` for one-call validate → prepare artifacts → backtest summary.
3. Update usage guide to prefer artifact workflow over inline JSON workflow.

### Phase 4 — Storage Optimization

1. Added SQLite persistence for backtest results (survive MCP restarts).
2. Added `content_hash` column to indicator artifacts.
3. Added hash-based artifact reuse — recomputing identical indicators returns the existing artifact.
4. Added light migration helper for new columns on existing databases.

### Remaining

- Columnar artifact storage (Parquet or row-oriented SQLite) for faster slicing.
- Result cache deduplication by strategy + params + artifact IDs.

---

## Success Criteria

The plan is successful when:

1. A 5min multi-year strategy can be run without returning raw/enriched bars to the agent.
2. Default backtest responses fit comfortably in chat context.
3. Full trades, equity, analytics, and bars remain retrievable on demand.
4. Agents can discover and reuse existing artifacts/results.
5. Artifact retention is explicit and safe.
6. Inline JSON workflows still work for small data, but are no longer the recommended default.

---

## Bottom Line

The optimization should not reduce data fidelity. It should reduce **unrequested data transfer**.

The target design is:

```text
full data stored server-side
compact summaries returned by default
stable IDs returned for follow-up access
pagination/filtering used for detail retrieval
explicit retention prevents surprise data loss
```
