# Scenarios — Backtest Trust and Leverage Correctness

Scenarios use Classical-school, black-box tests: real parser/use-case/engine objects, in-memory fakes for external boundaries, and assertions on observable results or started job payloads. Do not assert private helper calls.

---

### Scenario: Informative indicator jobs use declared timeframe intervals
**Priority:** Must  
**Slice:** 1

**Gherkin:**
  Given a valid multi-timeframe strategy with a declared informative timeframe alias and interval  
  When indicator jobs are started from the strategy definition  
  Then each informative job uses the interval declared for its alias, not a hard-coded fallback

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| definition | dict/JSON | strategy with `timeframes.informative=[{"alias":"weekly","interval":"1w"}]` | Required, schema_version `2.0` |
| symbol | string | `BTC` | Required, non-empty |
| source | string | `yfinance` | Required |
| params_json | dict | `{}` | Optional |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| primary job uses primary interval | Inspect fake job manager payload |
| weekly informative job uses `1w` | Inspect fake job manager payload |
| daily informative job uses `1d` | Inspect fake job manager payload |
| condition-referenced informative columns route to the right alias job | Inspect payload indicators grouped by alias |

**Verify (Classical school, black-box):**
```python
fake_manager = InMemoryIndicatorJobManager()
runner = NoOpIndicatorJobRunner()
use_case = ComputeStrategyIndicatorsUseCase(
    StrategyDefinitionParser(), fake_manager, runner
)

result = use_case.execute(definition_json, symbol="BTC", source="yfinance")

assert result.valid is True
assert fake_manager.started_payloads["primary"]["interval"] == "1d"
assert fake_manager.started_payloads["weekly"]["interval"] == "1w"
# Do NOT assert private interval-map helper calls.
```

**Also test:**
- Informative `1d` remains `1d`.
- Multiple informative aliases each use their own declared interval.
- Missing/unknown timeframe aliases still produce validation errors before job creation.

---

### Scenario: Warmup bars build strategy state but cannot trade
**Priority:** Must  
**Slice:** 2

**Gherkin:**
  Given required indicators are missing during warmup and valid after warmup  
  When a crossover is established on a warmup bar and completes on the first tradable bar  
  Then the strategy state includes the warmup bar and the first tradable crossover can trigger an entry

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| bars | list[dict] | enriched OHLCV bars with initial NaN values | Closed bars, sorted ascending |
| warmup_bars | int | `1` | >= 0 |
| condition | strategy condition | `fast crosses_above slow` | Valid runtime condition |
| initial_cash | float | `10000.0` | > 0 |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| warmup bars do not create trades | Inspect result trades/equity before first tradable |
| crossover state is seeded by warmup bar | First tradable bar entry occurs |
| no-warmup behaviour remains unchanged | Existing backtest tests still pass |
| trust diagnostics report warmup gating | Inspect `trust_diagnostics.warmup_bars` and `first_tradable` |

**Verify (Classical school, black-box):**
```python
result = backtest_use_case.execute(
    BacktestStrategyDefinitionRequest(
        definition=crossover_strategy,
        bars=enriched_bars,
        symbol="TEST",
        interval="1d",
    )
)

assert result.valid is True
assert result.result.warmup_bars == 1
assert result.result.total_trades == 1
assert result.result.trades[0]["entry_date"] == "2024-01-03"
# Do NOT inspect strategy._previous_values.
```

**Also test:**
- Warmup bar with an entry condition true does not place a pending entry.
- Exit signals during warmup do not close positions because no position can be opened during warmup.
- Strategies with no crossover still behave as before.

---

### Scenario: Leveraged liquidation uses maintenance margin consistently
**Priority:** Must  
**Slice:** 3

**Gherkin:**
  Given a leveraged position with a configured maintenance margin percentage  
  When price moves against the position  
  Then liquidation occurs at the maintenance-aware liquidation boundary and diagnostics disclose the model

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| leverage_multiplier | float | `3.0` | > 1 for leveraged liquidation |
| maintenance_margin_pct | float | `0.005` | >= 0 and < initial margin fraction |
| direction | enum | `long` / `short` | Required |
| entry_price | float | `100.0` | > 0 |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| long liquidation price is above zero-maintenance boundary | Compare calculated liquidation price |
| short liquidation price is below zero-maintenance boundary | Compare calculated liquidation price |
| price crossing liquidation boundary closes trade with reason `liquidation` | Inspect trade metadata |
| diagnostics disclose leverage, margin mode, maintenance margin, and liquidation model | Inspect `trust_diagnostics` |

**Verify (Classical school, black-box):**
```python
result = BacktestRunner().run(
    adverse_bars,
    OneShotLongStrategy(position_size=300),
    initial_cash=10000,
    leverage=3,
    maintenance_margin_pct=0.005,
)

trade = result["trades"][0]
assert trade["metadata"]["exit_reason"] == "liquidation"
assert result["trust_diagnostics"]["maintenance_margin_pct"] == 0.005
assert result["reconciliation_error"] == 0.0
```

**Also test:**
- `maintenance_margin_pct=0.0` preserves current zero-maintenance liquidation price.
- Invalid maintenance margin values are rejected or normalized with diagnostics.
- Full-margin and simplified modes agree on liquidation boundary when other assumptions match.

---

### Scenario: Risk prices can be based on actual entry fill
**Priority:** Should  
**Slice:** 4

**Gherkin:**
  Given a strategy signal is generated at one close price and filled at the next open  
  When execution is configured to use fill-based risk prices  
  Then stop and target prices are recalculated from the actual entry fill before position sizing and entry validation

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| risk_price_basis | enum | `signal_close` / `entry_fill` | Default preserves backward compatibility |
| stop_loss_type | enum | `fixed_pct` / `atr` / `none` | Existing risk modes |
| take_profit_type | enum | `risk_reward` / `fixed_pct` / `atr` / `none` | Existing risk modes |
| signal_close | float | `100.0` | > 0 |
| next_open | float | `110.0` | > 0 |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| `signal_close` basis preserves existing stop/target | Inspect trade stop/diagnostic or fill behaviour |
| `entry_fill` basis recalculates stop/target from next open | Inspect fill and resulting stop/target behaviour |
| position sizing uses the same stop that is actually attached to the position | Inspect trade size after forced stop |
| trust diagnostics disclose selected basis | Inspect `trust_diagnostics.risk_price_basis` |

**Verify (Classical school, black-box):**
```python
result = BacktestRunner().run(
    gap_up_bars,
    fixed_pct_risk_strategy,
    initial_cash=10000,
    risk_price_basis="entry_fill",
)

trade = result["trades"][0]
assert trade["entry_price"] == 110.0
assert trade["metadata"]["stop_price"] == 104.5
assert result["trust_diagnostics"]["risk_price_basis"] == "entry_fill"
```

**Also test:**
- Risk-reward target recalculates from fill-based stop.
- ATR-based risk uses ATR from the signal bar but price anchor from the entry fill.
- Existing default remains `signal_close` unless explicitly changed.

---

### Scenario: Borrow and funding assumptions are explicit and configurable
**Priority:** Should  
**Slice:** 5

**Gherkin:**
  Given a short or perpetual-style leveraged position  
  When borrow or funding costs are enabled  
  Then costs are applied according to a documented schedule and surfaced in reconciliation and trust diagnostics

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| borrow_fee_annual_pct | float | `0.05` | >= 0 |
| enable_funding | bool | `true` | Optional |
| funding_rate | float | `0.0001` | Signed or holder/side convention documented |
| funding_interval_bars | int | `8` | > 0 if scheduled funding enabled |
| timestamps | DatetimeIndex/string dates | hourly bars | Sorted ascending |

**Expected output / state change:**
| Assertion | How to verify |
|-----------|---------------|
| intraday borrow can accrue proportionally when timestamp-based mode is enabled | Compare with zero-borrow run |
| funding applies at configured schedule | Inspect `total_funding` and final equity |
| reconciliation remains zero after funding/borrow | Inspect `reconciliation_error` |
| diagnostics disclose cost schedule and simplifications | Inspect `trust_diagnostics` |

**Verify (Classical school, black-box):**
```python
result = BacktestRunner().run(
    hourly_short_bars,
    OneShotShortStrategy(position_size=10),
    initial_cash=10000,
    borrow_fee_annual_pct=0.05,
    borrow_time_basis="timestamp_delta",
)

assert result["total_borrow_cost"] > 0
assert result["final_value"] < no_borrow_result["final_value"]
assert result["reconciliation_error"] == 0.0
assert result["trust_diagnostics"]["borrow_time_basis"] == "timestamp_delta"
```

**Also test:**
- Current calendar-day borrow mode remains available for compatibility.
- Funding disabled produces `total_funding == 0`.
- Short funding sign convention is documented and tested.
