# Causal MTF Streaming Enrichment Parity

## User Story
As a trader running Finbar-authored strategies live through Finbot, I want Finbar backtests and Finbot WebSocket execution to use the same **causal multi-timeframe enrichment model**, so that every strategy decision in a backtest is based only on data that would have existed at that candle close in live trading.

## Problem Statement
Finbar currently has a parity-breaking gap for AMT / volume-profile based strategies, including `14_amt_value_reject_30m_1h_mtf.yaml`.

**The current full-frame session VP implementation is wrong for live-tradable backtests and must be replaced in all live-parity / production-validation paths.** It may remain only as an explicitly labelled research/batch mode for reproducing historical results, but it must not be used as the oracle for deployable strategies.

Finbot receives closed candles one at a time from WebSocket streams. At primary candle `t`, Finbot can only enrich with bars available up to `t` for the primary timeframe and up to the latest closed informative bar for each informative timeframe. This is the live-tradable, causal data horizon.

The current Finbar backtest path enriches a full historical frame in batch. For normal causal rolling indicators, the value at row `t` is identical whether computed from the full frame or from the prefix ending at `t`. However, the AMT / volume-profile fields used by the production MTF strategy are frame-length dependent. In a full-frame batch enrichment, early-row `vp_poc`, `vp_vah`, `vp_val`, and derived booleans such as `near_vah` and `rejection_from_edge` can be influenced by bars that occur after `t`. That makes the full-frame backtest an invalid oracle for live WebSocket behavior.

Concrete evidence from the Finbot parity investigation over committed SOL fixtures:

```text
row 17: 2026-06-07 16:30:00

field                  full-frame backtest     streaming-prefix/live
near_vah               False                   True
rejection_from_edge    False                   True
value_area_width_pct   3.124917877796119       1.3537219914089755
vp_poc                 64.25567                64.085818
vp_vah                 66.2123                 64.913476
vp_val                 64.14322                64.034728
```

Those value differences cause different first strategy signals before any fills, sizing, risk gates, or exchange simulation are involved:

```text
full-frame batch reference first signal:  row 95, 2026-06-09 07:30:00, short_entry
streaming-prefix reference first signal:  row 17, 2026-06-07 16:30:00, short_entry
Finbot live/replay first signal:          row 17, 2026-06-07 16:30:00, short_entry
```

This proves the divergence source is the enrichment model, not Finbot execution timing.

## Code-Level Root Cause

The current implementation confirms the observed behavior:

- `packages/strategy-runtime/finbar_strategy_runtime/domain/services/volume_profile.py`
  - `compute_all_session_volume_profiles(df)` groups by `df.index.date`.
  - For each date, it passes the **entire session DataFrame** to `compute_session_volume_profile(session)`.
  - It then broadcasts the resulting completed-session `poc/vah/val` back to every row in that date.
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/volume_profile.py`
  - `vp_poc`, `vp_vah`, `vp_val` call `compute_all_session_volume_profiles(df)` through `_compute_volume_profile()`.
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/handlers/market_profile_amt.py`
  - AMT fields (`near_vah`, `near_val`, `value_area_width_pct`, `rejection_from_edge`, etc.) derive from those `vp_*` columns.
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/multi_timeframe_bar_enricher.py`
  - The MTF merge is as-of/no-lookahead, but each timeframe's indicators are computed before the merge. Therefore indicator-level lookahead in `vp_*` happens before merge alignment can protect against it.
- `packages/strategy-runtime/finbar_strategy_runtime/indicators/streaming/windowed_indicator_state.py`
  - The current streaming fallback uses a fabricated hourly index (`pd.date_range("2024-01-01", ...)`) instead of preserving bar timestamps, so session/date-sensitive indicators cannot currently be trusted through the fallback either.

## Context
Existing spec `2026-06-16_streaming-indicator-calculator` defines an incremental indicator engine and batch↔streaming parity for scalar indicators. It explicitly leaves VP/AMT-style indicators as bounded-window recompute / windowed-default work. That is insufficient for live parity because the production strategy depends directly on AMT volume-profile outputs and MTF merged variants.

Existing spec `2026-06-20_finbot-package-parity-gaps` correctly states that Finbar backtest and Finbot live must share primitive enrichment/evaluation/sizing/fill functions. This new spec refines Gap #1: the shared enrichment primitive must be **causal** and support a streaming/live mode that Finbar backtests and Finbot both use when validating live-tradable behavior.

The desired package capability is not merely a faster indicator cache. It is a correctness contract and a replacement for the current live-validation enrichment path:

```text
For each closed primary bar t:
  enriched_live[t] == enriched_backtest_live_mode[t]
```

where both sides use only bars available by candle close `t`.

## Non-Goals
- Do not change Finbot in this spec. Finbot is the consumer; this spec belongs to Finbar because Finbar owns `finbar_strategy_runtime`.
- Do not change condition evaluation or crossover semantics.
- Do not change sizing/fill/PnL primitives.
- Do not claim the existing full-frame batch enrichment is suitable for live parity for AMT/VP indicators.
- Do not implement a performance-only cache unless it preserves the causal/live-mode correctness contract.
- Do not remove batch enrichment entirely; it may remain for research/exploration if clearly documented as non-live-parity for frame-dependent indicators.

## Initial Direction
Expose a package-level **causal MTF streaming enricher** that can be used by both:

1. Finbar backtests in live-parity mode.
2. Finbot live/replay processing.

The enricher should accept closed bars incrementally, maintain primary and informative timeframe state, and emit the latest enriched primary bar using only bars available at that point in time.

For live-parity `vp_poc`, `vp_vah`, and `vp_val`, this spec chooses **expanding current-session volume profile**:

```text
vp_at_bar[t] = volume_profile(session_bars from session open through bar t)
```

This exactly matches the causal behavior observed in Finbot's current WebSocket/prefix enrichment and can be reproduced in Finbar backtests without future leakage. Completed-session broadcast remains available only as `batch_full_frame` / research behavior and must be labelled not live-parity safe.
