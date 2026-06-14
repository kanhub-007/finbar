# Scenarios — Integrate New Market Metrics

All scenarios use the Classical (Detroit) school: real domain objects,
in-memory fakes at boundaries, assertions on outcomes (never on interactions).
No `mock.assert_called_once()`.

**Slice map:** 1 = Foundation → 2 = Microstructure handlers → 3 = Price-action
handlers → 4 = MCP/API discovery → 5 = Derivatives merge → 6 = New fetchers.

---

## Slice 1 — Foundation

### Scenario 1.1: Unified catalog serves both parser validation and capability checks
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a unified MetricCatalog that merges StrategyIndicatorCatalog and StaticMarketMetricCatalog
  When  the parser asks `supports_concrete("fib_618_retrace")`
  And   the capability layer asks `check("fib_618_retrace", "daily_ohlcv")`
  Then  both answer consistently (supported=True, computable=True)

**Input table:**
| Field            | Type   | Example            | Constraints       |
|------------------|--------|--------------------|-------------------|
| metric_name      | str    | "fib_618_retrace"  | Non-empty         |
| available_data   | str    | "daily_ohlcv"      | A DataClass value |

**Expected output / state change:**
| Assertion                                  | How to verify                       |
|--------------------------------------------|-------------------------------------|
| `catalog.supports_concrete("fib_618_retrace")` is True | Call the method, assert bool |
| `result = catalog.check(...)` → `result.computable is True` | Inspect MetricCapabilityResult |
| `result.confidence.value == "proxy"`       | Inspect confidence enum             |

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog

catalog = UnifiedMetricCatalog()

# Parser-side: name accepted
assert catalog.supports_concrete("fib_618_retrace") is True

# Capability-side: honest about computability
result = catalog.check("fib_618_retrace", "daily_ohlcv")
assert result.supported is True
assert result.computable is True
# Do NOT: assert "fib_618_retrace" in catalog._by_name  (white-box, tests internals)
```

**Also test:**
- Old names still work: `catalog.supports_concrete("sma_20")` → True
- Unknown name: `catalog.supports_concrete("nonexistent")` → False
- Name present but `implemented=False`: `check("elliott_wave_count", ...)` → `computable=False`


### Scenario 1.2: Rolling-window wrapper converts a scalar calculator to a Series
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a scalar calculator (e.g. `roll_spread`) that returns one float
  When  the wrapper applies it over a trailing N-bar window at each bar
  Then  the result is a Series with one value per bar (after warm-up)

**Input table:**
| Field     | Type         | Example                              | Constraints       |
|-----------|--------------|--------------------------------------|-------------------|
| calculator| Callable     | `roll_spread`                        | Pure function     |
| close     | pd.Series    | 30-bar random walk                   | Length ≥ window   |
| window    | int          | 20                                   | ≥ 2               |

**Expected output / state change:**
| Assertion                                  | How to verify                       |
|--------------------------------------------|-------------------------------------|
| Result is a `pd.Series` of same length     | `len(result) == len(close)`         |
| First `window-1` values are NaN            | `result.iloc[:window-1].isna().all()` |
| Last value is a finite float               | `np.isfinite(result.iloc[-1])`      |

**Verify (Classical school, black-box):**
```python
import numpy as np, pandas as pd
from finbar_strategy_runtime.indicators.rolling_scalar_wrapper import rolling_scalar_series
from finbar_strategy_runtime.domain.services.spread_proxies import roll_spread

np.random.seed(1)
close = pd.Series(100 + np.cumsum(np.random.randn(40) * 0.5))
result = rolling_scalar_series(roll_spread, close, window=20)

assert isinstance(result, pd.Series)
assert len(result) == len(close)
assert result.iloc[:19].isna().all()  # warm-up period
assert np.isfinite(result.iloc[-1])   # has a value after warm-up
```

**Also test:**
- `window` larger than data → all NaN (no crash)
- Calculator returns `None` for a window → that bar is NaN
- Window boundary: exactly `window` bars → first non-NaN at index `window-1`


### Scenario 1.3: Handler registration enforces name-sync invariant
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the unified catalog and the handler dispatch table
  When  a handler is registered for metric "X"
  Then  the catalog also lists "X" (or marks it implemented=False)
  And   if a catalogued name has no handler, check() returns computable=False

**Input table:**
| Field        | Type   | Example              | Constraints             |
|--------------|--------|----------------------|-------------------------|
| metric_name  | str    | "corwin_schultz_spread" | Registered in both   |

**Expected output / state change:**
| Assertion                                            | How to verify           |
|------------------------------------------------------|-------------------------|
| Every handler name is in the catalog                 | Set difference is empty |
| Catalogued-but-unimplemented metrics are not computable | `check(...).computable is False` |

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import _INDICATOR_HANDLERS

catalog = UnifiedMetricCatalog()
catalog_names = {name for name in catalog.all_metric_names()}
handler_names = set(_INDICATOR_HANDLERS.keys())

# Every handler must be catalogued (name-sync)
unregistered_handlers = handler_names - catalog_names
assert unregistered_handlers == set(), f"Handlers not in catalog: {unregistered_handlers}"

# Catalogued names without handlers must report implemented=False
for name in catalog_names - handler_names:
    result = catalog.check(name, "daily_ohlcv")
    assert result.computable is False or not result.supported
```


### Scenario 1.4: Unknown metric name rejected by parser
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a strategy YAML that references an unknown metric name in a condition
  When  the parser validates the definition
  Then  validation fails (`valid=False`) with an `unknown_operand` error

**Note on YAML schema:** Real strategies declare indicators with `name`,
`type`, and `timeframe` keys (see `strategies/amt_dip_buyer_final.yaml`).
Unknown names are caught when referenced as condition operands, producing
`code="unknown_operand"`. The validation result field is `valid` (not
`is_valid`).

**Verify (Classical school, black-box):**
```python
from finbar_strategy_runtime.parser.strategy_definition_parser import StrategyDefinitionParser

parser = StrategyDefinitionParser()
result = parser.parse({
    "schema_version": "2.0",
    "name": "bad",
    "timeframes": {"primary": "1d"},
    "indicators": [{"name": "close", "type": "close", "timeframe": "primary"}],
    "sides": {
        "long": {
            "entry": {
                "condition": {
                    "all": [
                        {"operator": ">", "left": "nonexistent_metric", "right": 100}
                    ]
                }
            }
        }
    },
})
assert result.valid is False
assert any(e.code == "unknown_operand" for e in result.errors)
```

---

## Slice 2 & 3 — OHLCV Metric Handlers

### Scenario 2.1: Strategy uses a new microstructure metric
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given OHLCV bars for BTC and a strategy requesting `corwin_schultz_spread`
  When  the indicator calculator computes it
  Then  the resulting DataFrame has a `corwin_schultz_spread` column

**Input table:**
| Field       | Type        | Example            | Constraints                |
|-------------|-------------|--------------------|----------------------------|
| df          | pd.DataFrame| 30 bars OHLCV      | Has open/high/low/close    |
| indicators  | list[str]   | ["corwin_schultz_spread"] | Names from catalog  |

**Expected output / state change:**
| Assertion                                          | How to verify                |
|----------------------------------------------------|------------------------------|
| `"corwin_schultz_spread" in result.columns`        | Check columns                |
| Values are non-negative floats (after warm-up)     | `(result[col].dropna() >= 0).all()` |

**Verify (Classical school, black-box):**
```python
import numpy as np, pandas as pd
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import PandasTaIndicatorCalculator

np.random.seed(1)
n = 30
close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.5))
df = pd.DataFrame({
    "open": close - 0.1, "high": close + 0.5, "low": close - 0.5,
    "close": close, "volume": np.random.randint(1000, 10000, n).astype(float),
})
df.index = pd.date_range("2024-01-01", periods=n, freq="D")

calc = PandasTaIndicatorCalculator()
result = calc.calculate(df, ["corwin_schultz_spread"])
assert "corwin_schultz_spread" in result.columns
assert (result["corwin_schultz_spread"].dropna() >= 0).all()
```


### Scenario 2.2: Metric needs a column not on the frame → all-NaN, no crash
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given a frame missing the `volume` column
  When  `amihud_illiq` is requested (it needs volume)
  Then  the handler produces an all-NaN column instead of raising

**Verify (Classical school, black-box):**
```python
import pandas as pd
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import PandasTaIndicatorCalculator

df = pd.DataFrame({"open":[1]*30, "high":[2]*30, "low":[0.5]*30, "close":[1.5]*30})
df.index = pd.date_range("2024-01-01", periods=30, freq="D")
calc = PandasTaIndicatorCalculator()
result = calc.calculate(df, ["amihud_illiq"])
assert "amihud_illiq" in result.columns
assert result["amihud_illiq"].isna().all()  # graceful, not a crash
```


### Scenario 2.3: Calculator throws internally → NaN column + warning logged
**Priority:** Must
**Slice:** 2

**Gherkin:**
  Given corrupt OHLCV data that makes a calculator raise
  When  the handler runs
  Then  the result column is all-NaN and a warning is logged (not an exception)

**Verify (Classical school, black-box):**
```python
import pandas as pd
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import PandasTaIndicatorCalculator

# Negative prices break log(high/low)
df = pd.DataFrame({"open":[-1]*30, "high":[-0.5]*30, "low":[-2]*30, "close":[-1]*30, "volume":[100]*30})
df.index = pd.date_range("2024-01-01", periods=30, freq="D")
calc = PandasTaIndicatorCalculator()
result = calc.calculate(df, ["parkinson_vol"])  # must not raise
assert "parkinson_vol" in result.columns
assert result["parkinson_vol"].isna().all()
```


### Scenario 3.1: Strategy uses a new price-action metric
**Priority:** Must
**Slice:** 3

**Gherkin:**
  Given OHLCV bars and a strategy requesting `fib_618_retrace`
  When  the calculator computes it
  Then  the frame has a `fib_618_retrace` column of floats

**Verify (Classical school, black-box):**
```python
import numpy as np, pandas as pd
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import PandasTaIndicatorCalculator

close = pd.Series(list(np.linspace(100, 200, 40)) + list(np.linspace(200, 150, 20)))
df = pd.DataFrame({"open": close, "high": close+1, "low": close-1, "close": close, "volume": 1000.0})
df.index = pd.date_range("2024-01-01", periods=len(close), freq="D")
calc = PandasTaIndicatorCalculator()
result = calc.calculate(df, ["fib_618_retrace"])
assert "fib_618_retrace" in result.columns
assert len(result["fib_618_retrace"]) == len(close)
```

---

## Slice 4 — MCP/API Discovery

### Scenario 4.1: list_market_metrics returns every metric with honest computability
**Priority:** Must
**Slice:** 4

**Gherkin:**
  Given the unified catalog is populated
  When  an MCP agent calls `list_market_metrics(symbol="BTC", source="hyperliquid", interval="1d")`
  Then  it receives a JSON list of all metrics, each with `computable`, `confidence`, `family`
  And   metrics needing intraday data show `computable: false` for daily

**Verify (Classical school, black-box):**

FastMCP tools are async. Tests use `pytest.mark.asyncio` and call
`await mcp.call_tool(...)`. The tool returns `(content_list, structured_dict)`
where `structured_dict` is the parsed result.

```python
import pytest
from finbar.presentation.mcp.tools.metrics_catalog import register_metric_catalog_tools
from fastmcp import FastMCP


@pytest.mark.asyncio
async def test_list_market_metrics():
    mcp = FastMCP("test")
    register_metric_catalog_tools(mcp)

    _content, payload = await mcp.call_tool(
        "list_market_metrics",
        {"symbol": "BTC", "source": "hyperliquid", "interval": "1d"},
    )
    assert isinstance(payload, list)
    names = {m["name"] for m in payload}
    assert "corwin_schultz_spread" in names
    spread = next(m for m in payload if m["name"] == "corwin_schultz_spread")
    assert isinstance(spread["computable"], bool)
```


### Scenario 4.2: check_metric returns capability for a single metric
**Priority:** Must
**Slice:** 4

**Gherkin:**
  When  an agent calls `check_metric("amihud_illiq", "daily_ohlcv")`
  Then  it gets `{supported: true, computable: true, confidence: "proxy", ...}`

**Verify (Classical school, black-box):**
```python
import pytest
from finbar.presentation.mcp.tools.metrics_catalog import register_metric_catalog_tools
from fastmcp import FastMCP


@pytest.mark.asyncio
async def test_check_metric():
    mcp = FastMCP("test")
    register_metric_catalog_tools(mcp)
    _content, payload = await mcp.call_tool(
        "check_metric", {"name": "amihud_illiq", "available_data_class": "daily_ohlcv"},
    )
    assert payload["supported"] is True
    assert payload["computable"] is True
```


### Scenario 4.3: resolve_metric performs dual-path resolution
**Priority:** Should
**Slice:** 4

**Gherkin:**
  Given the conceptual metric "volatility" has 3 resolution paths
  When  `resolve_metric("volatility", "daily_ohlcv", "1d")` is called
  Then  it selects `yang_zhang_vol` with confidence "proxy"
  When  `resolve_metric("volatility", "intraday_ohlcv", "5min")` is called
  Then  it selects `realized_vol_5m` with confidence "actual"

**Verify (Classical school, black-box):**
```python
import pytest
from finbar.presentation.mcp.tools.metrics_catalog import register_metric_catalog_tools
from fastmcp import FastMCP


@pytest.mark.asyncio
async def test_resolve_metric_dual_path():
    mcp = FastMCP("test")
    register_metric_catalog_tools(mcp)

    _c, daily = await mcp.call_tool(
        "resolve_metric",
        {"concept": "volatility", "available_data_class": "daily_ohlcv", "interval": "1d"},
    )
    assert daily["selected_metric"] == "yang_zhang_vol"
    assert daily["confidence"] == "proxy"

    _c, intraday = await mcp.call_tool(
        "resolve_metric",
        {"concept": "volatility", "available_data_class": "intraday_ohlcv", "interval": "5min"},
    )
    assert intraday["selected_metric"] == "realized_vol_5m"
    assert intraday["confidence"] == "actual"
```

---

## Slice 5 — Derivatives Merge

### Scenario 5.1: Derivatives data as-of merged onto OHLCV bars (no lookahead)
**Priority:** Must
**Slice:** 5

**Gherkin:**
  Given funding-rate rows persisted at hourly timestamps
  And   an OHLCV frame at hourly bars
  When  the derivatives merge handler runs
  Then  a funding value timestamped T appears only on bar T+1 (never T)
  And   bars before the first funding row are NaN

**Input table:**
| Field          | Type           | Example                    | Constraints       |
|----------------|----------------|----------------------------|-------------------|
| ohlcv          | pd.DataFrame   | hourly bars                | Datetime index    |
| funding_rows   | list[DerivativesMetrics] | hourly funding    | Timestamped       |
| interval       | str            | "1h"                       | Valid interval    |

**Expected output / state change:**
| Assertion                                          | How to verify                          |
|----------------------------------------------------|----------------------------------------|
| `funding_rate` column exists on the enriched frame | `"funding_rate" in result.columns`     |
| Bar at time T does NOT see funding at time T       | `result.loc[T, "funding_rate"]` is NaN |
| Bar at T+1 DOES see funding from T                 | `result.loc[T+1, "funding_rate"]` == funding_row.value |

**Verify (Classical school, black-box):**

The merger accepts `list[DerivativesMetrics]` (the frozen dataclass
from `finbar.core.domain.entities.derivatives_metrics`), matching what
`DerivativesRepository.find()` returns.

```python
import pandas as pd
from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from finbar.infrastructure.services.derivatives_merger import merge_derivatives_asof

ohlcv = pd.DataFrame(
    {"close": [100.0]*4},
    index=pd.date_range("2024-01-01 10:00", periods=4, freq="1h"),
)
funding_rows = [
    # funding stamped 10:00 visible at 11:00 bar, not 10:00
    DerivativesMetrics(symbol="BTC", timestamp="2024-01-01T10:00:00+00:00",
                       interval="1h", funding_rate=0.0001),
    DerivativesMetrics(symbol="BTC", timestamp="2024-01-01T11:00:00+00:00",
                       interval="1h", funding_rate=0.0002),
    DerivativesMetrics(symbol="BTC", timestamp="2024-01-01T12:00:00+00:00",
                       interval="1h", funding_rate=0.0003),
]
result = merge_derivatives_asof(ohlcv, funding_rows, interval="1h")
assert "funding_rate" in result.columns
# No lookahead: 10:00 bar must not see 10:00 funding
assert pd.isna(result.loc[result.index[0], "funding_rate"])
# 11:00 bar sees 10:00 funding
assert abs(result.loc[result.index[1], "funding_rate"] - 0.0001) < 1e-9
```

**Also test:**
- Empty funding list → column all-NaN, no crash
- Funding gap (missing hours) → forward-fill semantics (latest available)
- Interval offset correct: daily derivatives merged onto intraday bars use `+1d` offset


### Scenario 5.2: Derivatives metric usable in strategy condition
**Priority:** Must
**Slice:** 5

**Gherkin:**
  Given funding_rate data has been fetched and persisted
  And   a strategy YAML references `funding_rate` in an entry condition
  When  the backtest runs
  Then  the strategy can read `funding_rate` from the enriched bar dict

**Verify (Classical school, black-box):**
```python
# Integration test: strategy references a derivatives metric
from finbar.core.application.use_cases.backtest_strategy_definition import (
    BacktestStrategyDefinitionUseCase,
)
# ... set up bars with funding_rate column ...
# Assert the backtest completes and the condition evaluated against funding_rate
```


### Scenario 5.3: Derivatives not fetched → check_metric reports False with hint
**Priority:** Must
**Slice:** 5

**Gherkin:**
  Given no derivatives data in the repository for symbol "BTC"
  When  `check_metric("open_interest", "daily_ohlcv", symbol="BTC")` is called
  Then  `computable` is False
  And   the warning mentions running `fetch_derivatives` first

**Verify (Classical school, black-box):**

This test needs an in-memory fake of `DerivativesRepository`. Create one
at `tests/test_domain/fakes/in_memory_derivatives_repository.py` (returns
whatever list was injected via the constructor — classical school fake,
not a mock).

```python
from finbar.core.application.use_cases.check_metric_capability import CheckMetricCapabilityUseCase
from tests.test_domain.fakes.in_memory_derivatives_repository import (
    InMemoryDerivativesRepository,
)

# Fake (in-memory) repository — empty, simulating "never fetched"
fake_repo = InMemoryDerivativesRepository(data=[])
use_case = CheckMetricCapabilityUseCase(repository=fake_repo)
result = use_case.execute(name="open_interest", symbol="BTC", data_class="daily_ohlcv")
assert result.computable is False
assert any("fetch_derivatives" in w for w in result.warnings)
# Do NOT: mock_repo.find.assert_called_once()  (interaction testing)
```

---

## Slice 6 — New Fetchers

### Scenario 6.1: CoinGlass fetch_liquidations returns historical series
**Priority:** Should
**Slice:** 6

**Gherkin:**
  Given COINGLASS_API_KEY is set
  When  `fetch_liquidations("BTC", "1h")` is called
  Then  a list of DerivativesMetrics is returned with liquidations_long_1h etc. populated

**Verify (Classical school, black-box):**
```python
# Skip if no API key in CI
import os, pytest
pytestmark = pytest.mark.skipif(not os.getenv("COINGLASS_API_KEY"), reason="no key")

from finbar.infrastructure.services.coinglass_client import CoinGlassClient

client = CoinGlassClient()
metrics = client.fetch_liquidations("BTC", interval="1h", limit=10)
assert len(metrics) > 0
assert metrics[0].liquidations_long_1h is not None or metrics[0].liquidations_short_1h is not None
```


### Scenario 6.2: CoinGlass fetch_long_short_ratio returns historical series
**Priority:** Should
**Slice:** 6

**Verify (Classical school, black-box):**
```python
import os, pytest
pytestmark = pytest.mark.skipif(not os.getenv("COINGLASS_API_KEY"), reason="no key")

from finbar.infrastructure.services.coinglass_client import CoinGlassClient

client = CoinGlassClient()
metrics = client.fetch_long_short_ratio("BTC", interval="1h", limit=10)
assert len(metrics) > 0
assert metrics[0].long_short_ratio is not None
```


### Scenario 6.3: Hyperliquid fetch_funding_history returns hourly series (no API key)
**Priority:** Should
**Slice:** 6

**Verify (Classical school, black-box):**
```python
from finbar.infrastructure.services.hyperliquid_fetcher import HyperliquidFetcher

fetcher = HyperliquidFetcher()
bars = fetcher.fetch_funding_history("BTC", interval="1h")
assert len(bars) > 0
# Each row should have a funding_rate
assert bars[0].funding_rate is not None
```

**Also test:**
- HIP-3 symbol format `flx:TSLA` works
- Returns empty list for nonexistent symbol (no crash)
