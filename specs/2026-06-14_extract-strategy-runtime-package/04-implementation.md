# Implementation Guide — Extract Strategy Runtime Package

## Prerequisites
The file inventory in Finbot's `docs/FINBAR_RUNTIME_COPY.md` (at `Github/finbot/docs/FINBAR_RUNTIME_COPY.md`) is the authoritative reference for which files Finbot needs. This spec's extraction scope must include every file in that document's Tiers 1-6 plus any additional files Finbar's own backtesting/optimization runtime needs.

---

## Step 1: Create the package skeleton
**File:** `Github/finbar-strategy-runtime/pyproject.toml`

Create a standalone package with distribution name `finbar-strategy-runtime` and import name `finbar_strategy_runtime`. This lives in its own repository eventually; during development it may start inside `Github/finbar/packages/strategy-runtime/` with a note to extract before PyPI publish.

Dependencies:
```toml
[project]
name = "finbar-strategy-runtime"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
pandas = ["numpy>=1.26.0", "pandas>=2.0.0", "pandas-ta>=0.3.14"]
yaml = ["pyyaml>=6.0.0"]
dev = ["pytest>=8.0.0", "ruff>=0.6.0", "black>=24.0.0", "build>=1.2.0"]

[project.urls]
Repository = "https://github.com/..."
```

**Verify:** `python -m build` from the package root.

**Common mistake:** Do not add FastAPI, FastMCP, SQLAlchemy, yfinance, Hyperliquid, CoinGlass clients, or the `finbar` app as dependencies.

---

## Step 2: Define the package directory layout
**File:** `finbar_strategy_runtime/`

```
finbar_strategy_runtime/
  __init__.py
  domain/
    __init__.py
    entities/
      __init__.py                       # re-exports
      strategy_definition.py
      strategy_document.py
      condition.py
      condition_group.py
      operand.py
      indicator_spec.py
      feature_spec.py
      formula_node.py
      risk_spec.py
      side_rules.py
      signal_result.py
      strategy_parameter.py
      strategy_meta.py
      strategy_kind.py
      data_mode.py                      # REAL/PROXY enum used by StrategyMeta
      strategy_validation_error.py
      strategy_validation_result.py
      timeframe_declaration.py
      informative_timeframe.py
      volume_profile_result.py
    interfaces/
      __init__.py
      trading_strategy.py               # on_bar(bar, position) -> SignalResult
      strategy_definition_parser.py     # parse() -> StrategyValidationResult
      strategy_definition_strategy_factory.py  # create(definition) -> TradingStrategy
      strategy_feature_calculator.py
      formula_feature_calculator.py
      risk_price_calculator.py
      bar_frame_converter.py
      timeframe_bar_merger.py
      condition_tree_visitor.py
      indicator_calculator.py
      indicator_capability_provider.py
    services/                           # pure math functions (numpy/pandas only)
      __init__.py
      amt_signals.py
      auction_state.py
      volume_profile.py
      _profile_utils.py
      proxy_indicator.py
      market_profile.py
      profile_shape.py
      profile_shape_wrappers.py
      coil_detector.py
      composite_vp.py
      vwap_bands.py
      wyckoff_phase.py
      wyckoff_wrappers.py
      content_hash.py
  parser/
    __init__.py
    strategy_definition_parser.py       # main parser
    strategy_definition_serializer.py
    strategy_condition_parser.py
    strategy_condition_group_parser.py
    strategy_operand_parser.py
    strategy_parameter_resolver.py
    strategy_indicator_resolver.py
    strategy_feature_resolver.py
    strategy_risk_resolver.py
    strategy_timeframe_resolver.py
    strategy_definition_parse_helpers.py
    strategy_schema_provider.py
    strategy_indicator_catalog.py
    strategy_capability_service.py
    strategy_limit_rule.py
    strategy_limit_rules.py
    strategy_warning_rule.py
    strategy_warning_rules.py
    max_indicators_limit_rule.py
    max_features_limit_rule.py
    max_parameters_limit_rule.py
    max_condition_depth_limit_rule.py
    no_exit_warning_rule.py
    no_stop_warning_rule.py
    serialize_group_visitor.py
    description_visitor.py
    required_column_collector.py
    feature_input_column_collector.py
  evaluation/
    __init__.py
    condition_evaluator.py              # holds crossover state (stateful)
    json_rule_based_strategy.py         # TradingStrategy impl (stateful)
    json_risk_price_calculator.py       # stop/target pricing (stateless)
    strategy_definition_factory.py      # compiles definitions into strategies
  indicators/
    __init__.py
    pandas_indicator_calculator.py      # [pandas] extra, stateless
    pandas_strategy_feature_calculator.py
    pandas_formula_feature_calculator.py
    pandas_bar_frame_converter.py
    pandas_signal_calculator.py
    pandas_timeframe_bar_merger.py
    bar_merger.py                       # core merge logic
tests/
  contract/
    test_strategy_runtime_contract.py
conftest.py
```

**Design decisions in this layout:**

1. **`domain/services/`** holds the pure math functions (VP, AMT, proxies). These
depend only on numpy/pandas and domain entities. They are NOT application use
cases — they are pure computational services that both the indicator calculator
and future metric calculators call.

2. **`parser/`** is top-level, not under `core/application/`. The package has no
application layer (no use cases, no DTOs). The parser is a library service.

3. **`evaluation/`** groups the runtime evaluation engine: condition evaluator
(stateful), rule-based strategy (stateful), risk calculator (stateless),
and strategy definition factory (compiles definitions into executable strategies).

4. **`indicators/`** groups pandas-backed infrastructure that requires the
`[pandas]` extra. If pandas is not installed, importing this package raises a
clear `ImportError` with install instructions.

5. **`domain/services/` vs `indicators/`**: `domain/services/` contains pure
math that works on numpy arrays/pandas Series. `indicators/` contains the
pandas-ta-backed calculator that orchestrates multiple domain services and
returns a full enriched DataFrame.

**Verify:** `find finbar_strategy_runtime -name '*.py' | wc -l` roughly matches the inventory count.

**Common mistake:** Placing parser services in a `core/application/services/` path. The package has no application layer — parser lives at top-level `parser/`.

---

## Step 3: Move files and rewrite imports
**Files:** every file in the layout above.

Move from current Finbar locations:
- `finbar/core/domain/entities/*` → `finbar_strategy_runtime/domain/entities/`
- `finbar/core/domain/interfaces/*` → `finbar_strategy_runtime/domain/interfaces/`
- `finbar/core/application/services/strategy_*` → `finbar_strategy_runtime/parser/`
- `finbar/infrastructure/services/condition_evaluator.py` → `finbar_strategy_runtime/evaluation/`
- `finbar/infrastructure/services/json_rule_based_strategy.py` → `finbar_strategy_runtime/evaluation/`
- `finbar/infrastructure/services/json_risk_price_calculator.py` → `finbar_strategy_runtime/evaluation/`
- `finbar/infrastructure/services/strategy_definition_factory.py` → `finbar_strategy_runtime/evaluation/`
- `finbar/infrastructure/services/pandas_*` → `finbar_strategy_runtime/indicators/`
- `finbar/core/domain/services/amt_signals.py`, `auction_state.py`, `volume_profile.py`, `_profile_utils.py`, `proxy_indicator.py`, `market_profile.py`, `profile_shape.py`, `profile_shape_wrappers.py`, `coil_detector.py`, `composite_vp.py`, `vwap_bands.py`, `wyckoff_phase.py`, `wyckoff_wrappers.py`, `content_hash.py`, `confidence_scorer.py`, `indicator_value_mapper.py` → `finbar_strategy_runtime/domain/services/`
- `finbar/infrastructure/services/bar_merger.py` → `finbar_strategy_runtime/indicators/`

Replace all `from finbar.*` with `from finbar_strategy_runtime.*`.

**Verify:** `rg "from finbar|import finbar" finbar_strategy_runtime` returns zero production hits.

**Common mistake:** Accidentally moving Finbar use cases (`finbar/core/application/use_cases/`), DTOs (`finbar/core/application/dto/`), repositories, fetchers, backtest engine, or job managers. None of these belong in the package.

---

## Step 4: Add contract/parity tests before changing Finbar callers
**File:** `finbar_strategy_runtime/tests/contract/test_strategy_runtime_contract.py`

Use existing strategy fixtures from Finbar (`strategies/` directory) and synthetic enriched bars. Tests describe behaviour, not implementation calls.

**Minimum contract coverage (black-box, Classical school):**
1. Parse valid AMT dip buyer and AMT v2 strategies → valid result.
2. Parse strategy with unknown indicator → invalid, error path points to indicator name.
3. Parse strategy with unsupported operator → invalid.
4. Parse strategy with parameter override outside min/max → invalid.
5. Parse strategy with schema_version other than `"2.0"` → invalid.
6. Evaluate `is_true` condition on boolean bar → correct.
7. Evaluate `<`, `>`, `==`, `!=`, `<=`, `>=` on numeric bar → correct.
8. Evaluate `between` / `not_between` → correct.
9. Evaluate `crosses_above` with 2-bar sequence → triggers only on second bar.
10. Evaluate `crosses_below` with 2-bar sequence → triggers only on second bar.
11. Evaluate `all` group with 3 children (2 true, 1 false) → false.
12. Evaluate `any` group with 3 children (2 false, 1 true) → true.
13. Evaluate `not` group → negation correct.
14. Fallback operand sources used in order when primary is missing/NaN.
15. ATR stop with multiplier → correct stop price.
16. Fixed-pct stop → correct stop price.
17. Risk-reward take-profit → correct target.
18. Serialize definition to canonical dict → matches expected.
19. Compute atr, vp_poc, vp_vah, vp_val on fixture bars → columns present.
20. Compute acceptance_into_value on enriched bars → boolean column.
21. Compute dynamic period indicators (sma_37, rsi_21, atr_15) → correct values.
22. Compute parameterized VP (vp_poc_10d, rvp_vah_96, cvp_val_20d) → columns present.
23. Insufficient warmup (< min_bars) → safe NaN, no exception.
24. Reset evaluator crossover state → clean re-evaluation.

**Verify:** `pytest tests/contract`.

**Common mistake:** Testing private parser helpers or asserting method call counts.

---

## Step 5: Refactor Finbar to import the package
**File:** `Github/finbar/pyproject.toml`

During local development, add the runtime package as an editable dependency:
```
# in finbar's pyproject.toml (or use pip install -e)
"finbar-strategy-runtime[pandas,yaml] @ file:///path/to/finbar-strategy-runtime"
```

Then replace imports in Finbar strategy-related modules:
```python
# before
from finbar.core.domain.entities.strategy_definition import StrategyDefinition
# after
from finbar_strategy_runtime.domain.entities.strategy_definition import StrategyDefinition
```

Finbar-specific orchestration stays in:
- `finbar/core/application/use_cases/` — validates, enriches, backtests, saves, explains
- `finbar/infrastructure/repositories/` — SQL implementations
- `finbar/presentation/` — API routes, MCP tools, DTOs
- `finbar/startup/` — composition root, factories
- `finbar/infrastructure/services/backtest_runner.py` — backtest engine
- `finbar/infrastructure/services/grid_search_optimizer.py` — optimization
- `finbar/infrastructure/services/yfinance_stock_fetcher.py`, `hyperliquid_fetcher.py` — data fetching

**Verify:** `pytest tests` in `Github/finbar` — entire suite passes.

**Common mistake:** Letting the runtime package import Finbar to avoid a refactor. Dependency direction must be **Finbar → runtime package**, never runtime package → Finbar.

---

## Step 6: Preserve public API/MCP compatibility
**Files:** existing Finbar presentation DTOs, routes, MCP tools.

Keep public response shapes and tool names stable. If package object paths change relative to old Finbar paths, add mappers/adapters in Finbar. Compare saved normalized strategy JSON snapshots before and after the refactor.

**Verify:** Run existing API/MCP tests. Compare canonical strategy JSON snapshots.

**Common mistake:** Exposing package internal paths in API responses and breaking existing clients.

---

## Step 7: Publish only after all gates pass
**File:** package release workflow / CI.

Publish a pre-release `0.1.0a1` after:
- package contract tests pass in a clean venv (no Finbar installed),
- Finbar full test suite passes against the package,
- `rg "from finbar"` returns zero hits in package production code,
- strategy schema version metadata remains `"2.0"` in capabilities,
- no forbidden dependencies (FastAPI, FastMCP, SQLAlchemy, yfinance, Hyperliquid SDK).

**Verify:** `pip install finbar-strategy-runtime` in a clean venv and run `pytest tests/contract`.

**Common mistake:** Coupling schema version to package version. Package `0.2.0` may still support schema `"2.0"`.
