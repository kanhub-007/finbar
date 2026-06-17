## Domain Model

### Removed from Public API

| Component | File | Action |
|-----------|------|--------|
| `@_register("corwin_schultz_spread")` | `microstructure.py:78` | Remove decorator + handler function (lines 78–81) |
| `@_register("abdi_ranaldo_spread")` | `microstructure.py:88` | Remove decorator + handler function (lines 88–91) |
| `@_register("chung_zhang_spread")` | `microstructure.py:108` | Remove decorator + handler function (lines 108–111) |
| `MarketMetricDefinition("corwin_schultz_spread")` | `_metric_data.py:20` | Remove catalog entry |
| `MarketMetricDefinition("abdi_ranaldo_spread")` | `_metric_data.py:40` | Remove catalog entry |
| `MarketMetricDefinition("chung_zhang_spread")` | `_metric_data.py:71` | Remove catalog entry |

### Also Removed

| Component | File | Action |
|-----------|------|--------|
| Imports of the three domain functions | `microstructure.py:13–15` | Remove `_cs_calc`, `_ar_calc`, `_cz_calc` imports |
| Compound metric reference | `_metric_registry.py:120` | Remove `corwin_schultz_spread` from compound resolver if present |

### Preserved (NOT removed)

| Component | File | Reason |
|-----------|------|--------|
| `corwin_schultz_spread()` function | `spread_proxies.py:18` | Still imported by `informed_trading_proxies.py` and `resiliency_proxies.py` |
| `abdi_ranaldo_spread()` function | `spread_proxies.py:134` | Pure domain function — no internal consumers found, but harmless to keep |
| `chung_zhang_spread()` function | `spread_proxies.py:278` | Pure domain function — harmless to keep |

### Affected Tests

| Test File | Action |
|-----------|--------|
| `test_indicator_handlers_microstructure.py` | Remove `corwin_schultz_spread`, `abdi_ranaldo_spread`, `chung_zhang_spread` references |
| `test_market_metric_catalog.py` | Remove `corwin_schultz_spread` from assertions |
| `test_unified_catalog.py` | Remove `corwin_schultz_spread` references |
| `test_parser_accepts_new_metrics.py` | Remove `test_corwin_schultz_spread_accepted` |
| `test_api_metrics.py` | Remove `corwin_schultz_spread` from `test_list_includes_corwin_schultz` |
| `test_mcp_metrics_catalog.py` | Remove `corwin_schultz_spread` reference |
| `test_check_metric_capability.py` | Remove `corwin_schultz_spread` test |
| `test_microstructure_calculators.py` | Keep (tests domain functions, not handlers) |
