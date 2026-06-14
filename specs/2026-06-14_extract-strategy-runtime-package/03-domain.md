# Domain Model — Extract Strategy Runtime Package

## Entities
| Entity | Fields | Behaviour | Persisted? |
|--------|--------|-----------|------------|
| `StrategyDefinition` | schema_version, name, description, parameters, timeframes, indicators, features, risk, sides, metadata | Root parsed strategy contract | No, app persists snapshots |
| `StrategyDocument` | name, schema_version, description, definition_json, normalized_json, tags, created_at, updated_at | Saved strategy with metadata | No, app persists in SQL |
| `ConditionGroup` | kind (all/any/not/condition), children, condition | Nested boolean tree node | No |
| `Condition` | left: Operand, operator: str, right: Operand | Atomic comparison/bool/cross condition | No |
| `Operand` | kind (indicator/feature/field/constant/parameter), value, label, sources (fallback list), timeframe_alias | Resolves bar values with fallback chain | No |
| `RiskSpec` | stop_loss_type, stop_pct, stop_multiplier, stop_indicator, take_profit_type, take_profit_pct, risk_reward_ratio, take_profit_multiplier, take_profit_indicator | Risk price calculation inputs | No |
| `SideRules` | entry: ConditionGroup, exit: ConditionGroup, direction, entry_confidence, exit_confidence | Per-side signal rules | No |
| `SignalResult` | action (hold/entry/exit), side, confidence, stop_price, target_price, reason, context | Runtime output consumed by Finbar backtesting and Finbot order planning | App-specific persistence only |
| `IndicatorSpec` | name, type, period, timeframe_alias, fallbacks | Declares one enriched column | No |
| `FeatureSpec` | name, type, source, window, shift, raw_expr | Derived feature declaration | No |
| `FormulaNode` | operator, left, right, value, children | Expression AST for formula features | No |
| `StrategyParameter` | name, type, default, minimum, maximum, description | Typed runtime parameter | No |
| `StrategyMeta` | name, description, schema_version, kind, indicators, features, timeframes, side_count, has_stop_loss, has_take_profit | Metadata for TradingStrategy.meta() | No |
| `StrategyKind` | enum: BUILTIN / USER_DEFINED | Classifies strategy origin | No |
| `StrategyValidationError` | path, message, severity | Path-specific diagnostic | No |
| `StrategyValidationResult` | valid, definition, errors, warnings, required_columns, required_columns_by_timeframe, timeframe_declarations, warnings | Parse/validate result | No |
| `TimeframeDeclaration` | primary_interval, informative | Primary + up to 3 informative timeframes | No |
| `InformativeTimeframe` | alias, interval | Named informative timeframe | No |
| `Interval` | value string (1m, 5m, 1h, 1d, etc.) | Bar interval value object | No |

## Value Objects
| Name | Fields | Used where |
|------|--------|------------|
| `StrategySchemaVersion` | value string, e.g. `"2.0"` | Parser, serializer, package metadata |
| `RuntimePackageVersion` | semver string | Package distribution only; must not replace schema version |
| `IndicatorCapability` | name, period_range, data_requirements | Catalog and compatibility checks |
| `RuntimeCapabilityReport` | schema_versions, operators, indicators, features, risk_modes, feature_types | Finbar tools and Finbot compatibility |
| `CrossoverState` | dict[str, tuple[float, float]] | Mutable state for crosses_above/below tracking |

## Interfaces (for DI)
| Interface | Methods | Implemented by |
|-----------|---------|----------------|
| `StrategyDefinitionParser` | `parse(text, overrides=None) -> StrategyValidationResult` | Runtime parser |
| `StrategyDefinitionSerializer` | `to_dict(definition) -> dict` | Runtime serializer |
| `StrategyDefinitionStrategyFactory` | `create(definition) -> TradingStrategy` | Compiles parsed definition into executable strategy |
| `IndicatorCapabilityProvider` | `resolve(indicator_type, period)`, `supports_concrete(name)`, `as_dict()` | Runtime catalog |
| `IndicatorCalculator` | `calculate(frame, indicators) -> frame` | Pandas implementation; future alternatives |
| `StrategyFeatureCalculator` | `calculate(frame, features) -> frame` | Pandas implementation |
| `FormulaFeatureCalculator` | `evaluate(frame, formula_node) -> series` | Pandas implementation |
| `RiskPriceCalculator` | `calculate(risk, bar, side) -> tuple[float | None, float | None]` | JSON risk calculator |
| `TradingStrategy` | `on_bar(bar) -> SignalResult`, `on_reset()`, `meta() -> StrategyMeta` | Rule-based strategy |
| `ConditionTreeVisitor` | visit_group(group), visit_condition(condition) | Serializer, explainer, required-column collector |
| `BarFrameConverter` | `to_frame(bars)`, `from_frame(frame)` | Pandas converter |
| `TimeframeBarMerger` | `merge(primary, informative, informative_interval, columns)` | Pandas merger — takes full frames; callers extract last row for incremental use |

## What stays in Finbar (NOT in package)
- **Use cases:** `validate_strategy_definition.py`, `backtest_strategy_definition.py`, `save_strategy_definition.py`, `explain_strategy_definition.py`, `apply_indicators.py`, `apply_strategy_features.py`, `run_backtest.py`, `fetch_prices.py`, optimization and walk-forward use cases
- **DTOs:** all `core/application/dto/` files
- **Repositories:** all SQL implementations in `infrastructure/repositories/`
- **ORM tables:** all files in `infrastructure/tables/`
- **Backtest engine:** `backtest_runner.py`, `backtest_position.py`, `backtest_loop_state.py`, `backtest_data_validator.py`, `backtest_result_builder.py`, `position_*.py`, `intrabar_exit_resolver.py`, `margin_account_manager.py`
- **Optimization:** `grid_search_optimizer.py`, `walk_forward_optimizer.py`, `walk_forward_fold_helpers.py`
- **Job managers:** `in_memory_indicator_job_manager.py`, `in_memory_optimization_job_manager.py`, `fetch_job_manager.py`, `indicator_job_runner.py`
- **Fetchers:** `yfinance_stock_fetcher.py`, `hyperliquid_fetcher.py`, `coinglass_client.py`, `rate_limiter.py`
- **Data:** `connection.py`
- **Built-in strategy providers:** `builtin_strategy_provider.py`, `composite_strategy_provider.py`, `database_strategy_provider.py`
- **Presentation:** all files in `presentation/`
- **Startup:** all files in `startup/`
- **Domain services that only backtesting needs:** `backtest_metrics.py`, `confidence_scorer.py`, `correlation.py`, `rolling_metrics.py`, `annualization.py`
- **Domain services that compute from bars but are not runtime-required:** `coil_detector.py`, `composite_vp.py`, `market_profile.py`, `profile_shape.py`, `profile_shape_wrappers.py`, `vwap_bands.py`, `wyckoff_phase.py`, `wyckoff_wrappers.py` — these can move later or stay as adapters; decision deferred to implementation

## Package boundary
- **Allowed:** stdlib, `typing`, `dataclasses`, optional `numpy`, optional `pandas`, optional `pandas-ta`, optional `pyyaml` (if YAML parsing stays in package).
- **Forbidden:** FastAPI, FastMCP, SQLAlchemy, yfinance, Hyperliquid SDK, CoinGlass clients, Finbar startup/presentation/repositories, Finbot live-trading adapters.
- The package emits validation results, enriched bars, and signals. It never submits orders, fetches data, writes to databases, or starts servers.

## Statefulness contract (critical for both use cases)
The package has two kinds of components with different statefulness rules. Both
Finbar (batch backtesting) and Finbot (incremental live execution) must respect
these:

| Component | Stateful? | Who owns state? | Rules |
|-----------|----------|-----------------|-------|
| `TradingStrategy` | **Yes** | The strategy instance | Holds `_previous_values` dict for `crosses_above`/`crosses_below` crossover tracking. Call `on_reset()` before a new backtest run (Finbar) or on session restart (Finbot). |
| `ConditionEvaluator` | **Yes** | Held inside `JsonRuleBasedStrategy` | Crossover state committed per-bar via `commit()`. Never shared across strategies. |
| `IndicatorCalculator` | **No** | Stateless | Recomputes all indicator columns from a full DataFrame each call. Pass the full bar window, not just the latest bar. |
| `RiskPriceCalculator` | **No** | Stateless | Pure function: given RiskSpec + bar + side, returns stop/target. |
| `StrategyDefinitionParser` | **No** | Stateless | Pure function: text → StrategyValidationResult. |

**Finbar (batch) usage pattern:**
```python
strategy = factory.create(definition)  # one instance per backtest run
strategy.on_reset()                     # clear crossover state
enriched = calculator.calculate(full_df, required_indicators)  # enrich once
for bar in enriched.iter_dicts():       # iterate all bars
    signal = strategy.on_bar(bar, position_dict)  # state accumulates
```

**Finbot (incremental/live) usage pattern:**
```python
strategy = factory.create(definition)  # one instance per symbol per session
# NEVER recreate mid-session, NEVER share across symbols
for each closed candle:
    warmup_window.append(candle)
    enriched = calculator.calculate(warmup_window, required_indicators)  # recompute full window
    latest_bar = enriched.iloc[-1].to_dict()
    signal = strategy.on_bar(latest_bar, position_dict)  # crossover state persists
```
