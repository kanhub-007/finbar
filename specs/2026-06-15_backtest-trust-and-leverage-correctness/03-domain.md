# Domain Model — Backtest Trust and Leverage Correctness

## Entities
| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| `ExecutionConfig` | existing fields plus `risk_price_basis`, optional borrow/funding scheduling fields | Declares execution assumptions for one backtest run | No |
| `LeverageConfig` | multiplier, maintenance_margin_pct | Computes margin required and maintenance-aware liquidation price | No |
| `PendingEntry` | direction, stop_price, target_price, position_size, explicit_size, risk_per_trade, optional risk metadata | Carries a deferred next-open entry intent | No |
| `BacktestPosition` | size, direction, entry_price, stop_price, target_price, liquidation_price, bars_held, cost fields | Tracks open position state during a run | No |
| `TradeRecord` | entry/exit prices, size, gross/net PnL, costs, metadata | Completed round-trip record | App persists result snapshots only |
| `BacktestLoopState` | cash, position, pending orders, trades, equity curve, diagnostics, cost totals | Mutable state for one backtest run | No |
| `StrategyDefinition` | strategy schema fields from runtime package | Source of parsed strategy semantics | No |
| `SignalResult` | action, direction, confidence, stop_price, target_price, position_size, metadata | Runtime signal emitted per bar | No |
| `BacktestDiagnostic` | severity, code, date, message, metadata | Records trust/accounting/order diagnostics | App persists result snapshots only |

## Value Objects
| Name | Fields | Used where |
|------|--------|------------|
| `RiskPriceBasis` | enum string: `signal_close`, `entry_fill` | `ExecutionConfig`, risk/entry handling |
| `LiquidationModel` | enum string: `isolated_zero_maintenance`, `isolated_maintenance_margin` | Trust diagnostics and leverage calculator |
| `BorrowTimeBasis` | enum string: `calendar_day`, `timestamp_delta` | Borrow cost calculation |
| `FundingSchedule` | mode/interval fields | Funding cost calculation |
| `WarmupPolicy` | warmup_bars, first_tradable, allow_state_updates | Backtest runner gating |

## Domain Services
| Service | Responsibility | Layer |
|---------|----------------|-------|
| `LiquidationPriceCalculator` or enhanced `LeverageConfig` | Pure maintenance-aware liquidation calculation | `core/domain/` |
| `BorrowCostCalculator` | Pure borrow cost from notional, annual rate, and elapsed time | `core/domain/services/` or infrastructure service if timestamp parsing remains there |
| `FundingCostCalculator` | Pure funding schedule calculation | `core/domain/services/` or infrastructure service |
| `RiskPriceRebaser` | Converts signal-close risk prices/specs to entry-fill anchored prices where configured | Prefer infrastructure/backtest service unless runtime exposes reusable pure calculator |
| `WarmupTradeGate` | Decides whether a bar may create/execute orders while still allowing strategy state updates | Infrastructure backtest service |

## Interfaces (for DI)
| Interface | Methods | Implemented by |
|-----------|---------|----------------|
| `BacktestEngine` | `run(df, strategy, initial_cash, **params) -> dict` | `BacktestRunner` |
| `TradingStrategy` | `on_bar(bar, position) -> SignalResult`, `on_reset()`, `meta()` | Runtime strategies and test fakes |
| `StrategyDefinitionParser` | `parse(text, overrides=None) -> StrategyValidationResult` | Runtime parser |
| `IndicatorJobManager` | `start(payload, runner)` | Real job manager; in-memory fake in tests |
| `IndicatorJobRunner` | `run(...)` | Real runner; no-op fake in tests |

## Entity vs ORM separation
- Backtest runtime entities remain pure Python/domain entities; no ORM classes are introduced.
- Persisted backtest results continue to use existing result-store mechanisms outside this feature.
- Strategy runtime entities stay in `packages/strategy-runtime/finbar_strategy_runtime/domain/entities/`.
- Finbar-specific backtest execution stays in `finbar/infrastructure/services/` and application orchestration stays in `finbar/core/application/use_cases/`.

## Invariants
- Strategy parsing must reject invalid strategy semantics before any indicator/backtest jobs run.
- A bar can update strategy state without being tradable during warmup.
- Pending entries and signal exits fill at the next bar open.
- Stops/targets remain gap-aware.
- Position sizing must use the same stop level that will be attached to the actual position.
- Reconciliation must remain zero after realized PnL, funding, borrow, and fees are accounted for.
- Trust diagnostics must disclose every material execution assumption: entry model, exit model, costs, leverage, margin mode, maintenance margin, liquidation model, warmup policy, risk price basis, borrow basis, and funding schedule.
