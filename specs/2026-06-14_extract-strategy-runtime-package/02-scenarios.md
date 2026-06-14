# Scenarios — Extract Strategy Runtime Package

Scenarios use Classical-school, black-box tests: real runtime objects, in-memory fakes for boundaries, and assertions on outcomes/serialized contracts.

---

### Scenario: Runtime package exposes canonical strategy parsing and validation
**Priority:** Must  
**Slice:** 1

**Gherkin:**
  Given a valid Finbar strategy YAML/JSON definition
  When the definition is parsed through the extracted runtime package
  Then the same `StrategyDefinition` semantics and validation diagnostics are produced as current Finbar

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| definition_text | string | YAML/JSON strategy | Required, schema_version `2.0` |
| parameter_overrides | dict | `{}` | Optional, known parameter names only |
| expected_schema_version | string | `2.0` | Schema version is separate from package semver |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| parsed definition name/parameters/sides match current Finbar | Compare public dataclass fields |
| invalid definitions return path-specific validation errors | Inspect validation result |
| package has no imports from `finbar.presentation`, `finbar.startup`, repositories, or fetchers | Architecture test |

**Verify (Classical school, black-box):**
```python
parser = StrategyDefinitionParser()
result = parser.parse(valid_strategy_yaml)

assert result.valid is True
assert result.definition.name == "AMT Dip Buyer"
assert result.definition.schema_version == "2.0"
assert result.definition.sides["long"].entry is not None
# Do NOT assert private parser step calls.
```

**Also test:**
- Unknown indicator -> invalid with JSON path.
- Unsupported operator -> invalid with JSON path.
- Parameter override outside min/max -> invalid.
- Schema version other than `2.0` -> invalid until explicitly supported.

---

### Scenario: Runtime package evaluates strategy conditions and risk prices with Finbar parity
**Priority:** Must  
**Slice:** 1

**Gherkin:**
  Given a parsed strategy definition and enriched bars
  When the runtime evaluator processes bars in sequence
  Then entry/exit signals, crossover state, stop prices, and target prices match current Finbar behaviour

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bars | list[dict] | enriched OHLCV bars | Closed bars, sorted ascending |
| definition | StrategyDefinition | parsed strategy | Valid |
| side | enum | `long` | `long` or `short` |
| previous_values | dict | crossover state | Mutable state owned by evaluator |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| boolean and numeric operators produce same result | Inspect signal results |
| `crosses_above/below` only triggers after previous value exists | Run two-bar sequence |
| ATR/fixed/risk-reward risk prices match current Finbar | Inspect returned signal/risk tuple |
| evaluator emits signals only; it does not create orders | Public API has no order/exchange dependency |

**Verify (Classical school, black-box):**
```python
definition = parser.parse(strategy_yaml).definition
evaluator = RuleBasedStrategyEvaluator(definition, risk_calculator=JsonRiskPriceCalculator())

first = evaluator.on_bar(bar_before_cross)
second = evaluator.on_bar(bar_after_cross)

assert first.action in {"hold", "exit", "entry"}
assert second.stop_price == expected_stop
assert second.target_price == expected_target
```

**Also test:**
- `None`, missing, and NaN operand values evaluate safely.
- Fallback operand sources are used in order.
- Short side risk prices mirror long side behaviour.
- Repeated evaluation after reset starts from clean crossover state.

---

### Scenario: Runtime package computes existing indicator/enrichment columns with parity
**Priority:** Must  
**Slice:** 2

**Gherkin:**
  Given raw OHLCV bars and a list of supported runtime indicators
  When indicators are calculated through the extracted package
  Then output columns match current Finbar for existing indicators within numerical tolerance

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bars | DataFrame/list[dict] | OHLCV bars | Required columns: open/high/low/close/volume |
| indicators | list[string] | `["atr", "vp_vah", "acceptance_into_value"]` | Supported by runtime catalog |
| tolerance | float | `1e-9` | For numeric comparisons |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| requested columns exist when enough bars are present | Inspect enriched frame |
| AMT/profile/proxy columns match current Finbar | Compare fixtures |
| insufficient warmup produces safe NaN/missing outcomes, not exceptions | Inspect enriched frame/result |

**Verify (Classical school, black-box):**
```python
calculator = PandasIndicatorCalculator()
enriched = calculator.calculate(raw_bars_df, ["atr", "vp_poc", "vp_vah", "vp_val"])

assert {"atr", "vp_poc", "vp_vah", "vp_val"}.issubset(enriched.columns)
assert len(enriched) == len(raw_bars_df)
```

**Also test:**
- Dynamic period indicators (`sma_37`, `rsi_21`, `atr_20`).
- Parameterized VP (`vp_poc_10d`, `rvp_vah_96`, `cvp_val_20d`).
- Daily bars and intraday bars.
- Indicator requests with unknown names fail clearly or warn consistently with existing behaviour.

---

### Scenario: Finbar consumes the package without changing public tool behaviour
**Priority:** Must  
**Slice:** 3

**Gherkin:**
  Given Finbar has been refactored to import the extracted runtime package
  When existing Finbar MCP/API/use-case workflows validate, enrich, backtest, explain, and save a strategy
  Then public responses and persisted strategy definitions remain backwards compatible

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| strategy_definition | YAML/JSON | existing fixture | Valid under schema `2.0` |
| workflow | enum | validate/enrich/backtest/explain/save | Existing public use cases |
| bars_artifact_id | string | indicator artifact id | Existing Finbar artifact mechanism |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| existing Finbar tests still pass | Full test suite |
| API/MCP response shape remains compatible | Public DTO assertions |
| saved normalized JSON is unchanged | Compare snapshot/canonical dict |
| package imports do not invert Clean Architecture dependencies | Architecture tests |

**Verify (Classical school, black-box):**
```python
validate = make_validate_strategy_definition_use_case()
result = validate.execute(strategy_yaml)

assert result.valid is True
assert result.definition.name

pipeline = make_run_strategy_pipeline_use_case()
pipeline_result = pipeline.execute(strategy_yaml, symbol="BTC", interval="1h")
assert pipeline_result.validation.valid is True
```

**Also test:**
- Existing saved strategies load after refactor.
- Backtest signals/trades are unchanged for fixture data.
- Explanation text is unchanged or changes only in approved wording.
- Finbar startup still wires app-specific repositories/fetchers outside the package.

---

### Scenario: Runtime package can be built and installed independently
**Priority:** Should  
**Slice:** 3

**Gherkin:**
  Given the runtime package source is isolated
  When a wheel is built and installed in a clean environment
  Then parser/evaluator/indicator contract tests pass without the Finbar application installed

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| package_name | string | `finbar-strategy-runtime` | PyPI distribution name |
| import_name | string | `finbar_strategy_runtime` | Python import package |
| python_version | string | `3.12` | Match project support |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| wheel builds | `python -m build` |
| package imports without Finbar | clean venv smoke test |
| contract tests pass | `pytest tests/contract` |
| optional pandas extras are declared separately if needed | Inspect package metadata |

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.parser.strategy_definition_parser import StrategyDefinitionParser

result = StrategyDefinitionParser().parse(valid_strategy_yaml)
assert result.valid is True
```

**Also test:**
- Install minimal package without pandas extras if a minimal mode is supported.
- Install with `[pandas]` extra and compute indicators.
- Package metadata declares strategy schema version separately from package version.
