# Scenarios — Fix Metric Documentation Errors

---

### Scenario: cumulative_volume_delta appears in one section only
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given METRIC_CATALOG.md sections 10 (Order Flow) and 18 (Derivatives)
  When a reader searches for cumulative_volume_delta
  Then it appears in §10 as an OHLCV-derived proxy, and §18 cross-references it (no duplicate row)

**Input table:**
| Field | Type | Example | Constraints |
|-------|------|---------|-------------|
| Documentation file | path | docs/METRIC_CATALOG.md | Must exist |
| Metric name | string | cumulative_volume_delta | Listed once in catalog tables |

**Expected output:**
| Assertion | How to verify |
|-----------|---------------|
| §10 table has `cumulative_volume_delta` row | grep "cumulative_volume_delta" in §10 section |
| §18 does NOT have a `cumulative_volume_delta` table row | grep "cumulative_volume_delta" in §18 — only cross-reference text, no table row |
| §18 mentions it as "see §10" or similar | Human review of §18 text |

**Verify:**
```bash
# Count table-row occurrences of cumulative_volume_delta in METRIC_CATALOG.md
grep -c "cumulative_volume_delta" docs/METRIC_CATALOG.md
# Should be: §10 has it in the table, §18 mentions it in prose → 2 occurrences acceptable
# Should NOT be: two table rows with same indicator name
```

---

### Scenario: proxy_atr docs no longer say "Requires atr"
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given QUANTITATIVE_PROXIES.md section 1 (Daily → Intraday Structure Proxies)
  When a reader looks at the proxy_atr description
  Then it does NOT claim proxy_atr requires the `atr` indicator as a companion

**Verify:**
```bash
grep -A2 "proxy_atr" docs/QUANTITATIVE_PROXIES.md
# Should NOT contain: "Requires `atr` indicator"
# Instead should say something like: "Computed from high/low/close; no companion indicator needed."
```

---

### Scenario: Proxy compatibility matrix uses ⚠️ instead of N/A for intraday
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given METRIC_CATALOG.md §19 (Quantitative Proxies) and §21 (Data Class Compatibility Matrix)
  When a reader checks if proxies work on intraday data
  Then the matrix shows "⚠️" (proxy, prefer real) instead of "N/A"

**Verify:**
```bash
# The compatibility matrix row for "Quantitative Proxies" on intraday should show ⚠️ not N/A
grep -A1 "Quantitative Proxies" docs/METRIC_CATALOG.md | grep "⚠️"
# Should find ⚠️ for intraday column
```

---

### Scenario: Every metric table has a "Requires" column
**Priority:** Should
**Slice:** 2

**Gherkin:**
  Given any metric table in METRIC_CATALOG.md
  When a reader looks at a row for a dependent indicator
  Then a "Requires" column lists the companion indicators needed

**Example change:**
```markdown
| Indicator | Daily | Intraday | Requires | Description |
|-----------|-------|----------|----------|-------------|
| `trend_direction` | ✅ | ✅ | sma_20, sma_50, sma_200 | Trend direction (+1 up, -1 down, 0 flat) |
| `breakout_signal` | ✅ | ✅ | breakout_level, swing_low_20 | Breakout signal (+1 / -1 / 0) |
| `wyckoff_phase` | ✅ | ✅ | profile_shape | Current Wyckoff phase |
```

**Verify:**
- §1 (Traditional TA): trend_direction, trend_strength, trend_status, price_vs_sma20, breakout_level, breakout_signal, breakout_quality, is_power_zone, vol_buffer_high, vol_buffer_low have "Requires" filled in
- §3 (Wyckoff/VSA): wyckoff_phase has "profile_shape" in Requires
- §10 (Order Flow): cumulative_volume_delta is listed here (not in §18)

---

### Scenario: hurst_exponent docs note full-series broadcast behavior
**Priority:** Could
**Slice:** 2

**Gherkin:**
  Given METRIC_CATALOG.md §7 (Bill Williams / Chaos Theory)
  When a reader looks at the hurst_exponent row
  Then the description notes it is a single scalar broadcast across all bars, not a rolling window

**Verify:**
```bash
grep "hurst_exponent" docs/METRIC_CATALOG.md
# Description should contain: "full-series" or "broadcast" or "not rolling"
```

---

### Scenario: Unreliable spread estimators removed from docs
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given METRIC_CATALOG.md §8 and QUANTITATIVE_PROXIES.md §2
  When a reader looks at available spread estimators
  Then `corwin_schultz_spread`, `abdi_ranaldo_spread`, and `chung_zhang_spread` are absent (removed per spec `2026-06-17_remove-unreliable-spread-estimators`)

**Verify:**
```bash
grep "corwin_schultz_spread\|abdi_ranaldo_spread\|chung_zhang_spread" docs/METRIC_CATALOG.md
# No table rows for these three
grep "corwin_schultz_spread\|abdi_ranaldo_spread\|chung_zhang_spread" docs/QUANTITATIVE_PROXIES.md
# No references
```
