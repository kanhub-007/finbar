# All-Metrics Causal Streaming Parity

## User Story
As a trader using Finbar for backtests and Finbot for live execution, I want **every supported strategy metric** to be computed by one shared **causal streaming enrichment package**, so that a strategy decision at candle close uses only information available at that close, Finbar backtests are realistic by default, and Finbot can call the same package code instead of reimplementing indicator logic.

## Context
`2026-06-21_causal-mtf-streaming-enrichment-parity` made the production AMT MTF strategy causal and flipped JSON-strategy backtests to `live_parity_streaming` by default. A follow-up catalog sweep showed that the streaming path is not yet correct for all metrics:

| Category | Count | Behaviour | Examples |
|---|---:|---|---|
| Correct / acceptable drift | ~205 | Streaming latest value matches the causal prefix oracle | SMA/EMA/RSI/ATR, many price-action/microstructure metrics, session AMT/VP used by the production strategy |
| Silent wrong value | 22 | Returns a plausible scalar, but it differs from the causal prefix oracle; strategies can trade on wrong data without error | `vwap`, `rvp_poc_48/96/336`, `rvp_vah_*`, `rvp_val_*`, `alligator_jaw/teeth`, `cumulative_signed_volume_ofi`, `daily_vpin`, `empirical_volume_curve`, `intraday_volume_curve`, `is_b_shape`, `is_neutral_shape`, `parametric_u_shape`, `proxy_atr`, `proxy_expected_move`, `proxy_iv` |
| Loud NaN/raise | 23 | Returns NaN or raises; warmup validation catches it, so the backtest fails loudly | `hurst_exponent`, `realized_kurtosis/skewness/vol_5m`, `bipower_variation`, `daily_return_kurtosis/skewness`, `return_volume_correlation`, all `cvp_*`, `vp_poc/vah/val_5d/20d` |

The current problem is not that the strategy parser rejects these names — it accepts them. The problem is that the causal streaming engine either computes some incorrectly or cannot produce them. Once `live_parity_streaming` is the default, this becomes a correctness issue for every strategy using those metrics.

This spec makes the shared package (`finbar_strategy_runtime`) own the complete causal enrichment contract:

1. **Correctness oracle:** for any metric and any row `t`, the streaming value at `t` must equal the metric computed on the **prefix frame** ending at `t` (`bars[:t+1]`) and taking that last row. It must not equal a full-frame batch value that can see future bars in the same session.
2. **Package ownership:** Finbar and Finbot both call the package-level causal enricher. Neither app owns indicator semantics.
3. **Backtest safety:** Finbar backtests default to the causal path only when the required metrics are streaming-correct. During rollout, unsupported metrics trigger a loud fallback/diagnostic; after completion, the unsupported set is empty.
4. **Finbot contract:** Finbot consumes the same causal enricher and coverage classifier from the package for live/replay. Finbot owns its loop and exchange I/O; the package owns enrichment semantics.

## Non-Goals
- Do not change execution primitives: fills, sizing, PnL, leverage, liquidation, slippage, commission, and funding remain unchanged.
- Do not remove `batch_full_frame`; it remains a research/repro mode and may intentionally produce non-causal results.
- Do not change strategy schema, parser, rule evaluation, or crossover state semantics.
- Do not add new metric names. This spec fixes semantics for existing catalog metrics.
- Do not implement Finbot app wiring in this repo. This spec defines and tests the package contract that Finbot will consume.
- Do not require all metrics to be O(1) immediately. Some may use dedicated bounded state, session state, or prefix-safe windowed recompute, but every metric must be **causally correct**.

## Relationship to Existing Specs
- Extends `2026-06-16_streaming-indicator-calculator`: the windowed-default rule was adoptability-focused; this spec tightens it to full causal correctness for all catalog metrics.
- Extends `2026-06-20_finbot-package-parity-gaps`: Finbot consumes shared primitives; this spec completes Layer A (bar → enriched bar) as a causal streaming primitive.
- Extends `2026-06-21_causal-mtf-streaming-enrichment-parity`: the AMT strategy parity work becomes one case in a full-catalog causal parity matrix.
- Supersedes the metric-coverage slice inside `2026-06-21_causal-saved-strategy-backtest`; saved-strategy backtests should depend on this spec's completed package contract.
