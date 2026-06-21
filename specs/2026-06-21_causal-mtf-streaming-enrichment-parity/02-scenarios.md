# Scenarios — Causal MTF Streaming Enrichment Parity

Scenarios are ordered by priority. The first slice is a diagnosis/fix slice: prove the current full-frame AMT/VP enrichment leaks future session information, then introduce a causal streaming reference that Finbar and Finbot can both call.

All Verify blocks follow Classical school + black-box style: real calculators, real strategy definition, committed OHLCV fixtures, assertions on returned enriched values / signals / trades. No interaction assertions.

---

### Scenario 1: Full-frame session VP differs from streaming-prefix VP on the same row
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the production MTF AMT strategy and committed SOL OHLCV fixtures
  When  the package enriches row 17 using the full 500-bar frame
  And   the package enriches row 17 using only the prefix ending at row 17
  Then  `vp_poc`, `vp_vah`, `vp_val`, and derived AMT booleans differ
  And   the test documents that full-frame batch session VP is not a live-parity oracle

**Input table:**
| Field | Type | Example | Constraints |
|---|---|---|---|
| strategy | YAML | `14_amt_value_reject_30m_1h_mtf.yaml` | Production MTF AMT strategy |
| primary_bars | list[OHLCV] | SOL 30m, 500 bars | Sorted ascending |
| informative_bars | dict[str, list[OHLCV]] | `h1`: SOL 1h, 600 bars | Sorted ascending |
| row | int | 17 | Same row in both frames |

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| `full.iloc[17]["vp_vah"] != prefix.iloc[17]["vp_vah"]` | Compare values |
| `full.iloc[17]["near_vah"] != prefix.iloc[17]["near_vah"]` | Compare booleans |
| `full.iloc[17]["rejection_from_edge"] != prefix.iloc[17]["rejection_from_edge"]` | Compare booleans |

**Verify (Classical + black-box):**
```python
primary = load_sol_30m(limit=500)
info = {"h1": load_sol_1h(limit=600)}
enricher = build_shared_mtf_enricher(strategy)

full = enricher.enrich(primary, info)
prefix = enricher.enrich(primary[:18], info)

assert full.index[17] == prefix.index[17]
assert full["vp_vah"].iloc[17] != prefix["vp_vah"].iloc[17]
assert full["near_vah"].iloc[17] != prefix["near_vah"].iloc[17]
assert full["rejection_from_edge"].iloc[17] != prefix["rejection_from_edge"].iloc[17]
```

**Also test:**
- Row 200 still differs for session VP/AMT columns, proving the issue is not only an early warmup artifact.
- Scalar causal indicators (`atr`, `poc_slope_5_1h` when derived causally) either match or have explicitly documented tolerance.

---

### Scenario 2: Streaming-prefix reference signal matches Finbot live/replay first signal
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given the production MTF AMT strategy and the same SOL fixtures
  When  a reference loop enriches each bar from the prefix available at that bar
  Then  the first non-HOLD signal occurs at row 17 (`2026-06-07 16:30:00`) and is a short entry
  And   this matches Finbot live/replay behavior

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| first streaming-prefix signal row == 17 | Inspect reference loop output |
| first streaming-prefix signal action == short entry | Inspect `SignalResult` / mapped `SignalDecision` |

**Verify:**
```python
strategy = JsonRuleBasedStrategy(definition)
for i in range(len(primary)):
    enriched = enricher.enrich(primary[: i + 1], info_bars_available_at(i))
    readiness = validator.validate(enriched, required_columns)
    latest = enriched.iloc[-1].to_dict()
    if not tradable(readiness, len(enriched) - 1):
        strategy.on_bar(latest, flat_position)  # state only
        continue
    signal = strategy.on_bar(latest, flat_position)
    if signal.action != "hold":
        assert i == 17
        assert signal.action == "sell"
        assert signal.direction == "short"
        break
```

**Also test:**
- The full-frame batch reference first signal remains row 95 until the implementation changes, documenting the current defect.
- Once fixed, full-frame live-parity mode and streaming-prefix mode must both return row 17.

---

### Scenario 3: Backtest live-parity mode uses causal MTF streaming enrichment
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given a Finbar backtest configured for live parity
  When  the backtest processes primary bars in order
  Then  every strategy decision receives the latest causal enriched bar from the shared MTF streaming enricher
  And   no row uses future primary or future informative bars

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| `enriched_live_mode[i] == streaming_enricher.update(primary[i]).latest` for required columns | Compare row dicts |
| Informative values at primary row `i` come from the latest informative bar closed at or before primary close `i` | Inspect merged informative timestamp / suffix columns |

**Verify:**
```python
streaming = CausalMultiTimeframeStreamingEnricher(definition, indicators)
backtest = BacktestRunner(enrichment_mode="live_parity", enricher=streaming)

result = backtest.run(primary, informative={"h1": info})
reference = run_streaming_reference(primary, info)

assert result.first_signal == reference.first_signal
assert result.trades == reference.trades
```

**Also test:**
- Single-timeframe strategies still work.
- Multiple informative timeframes are independently gated by alias.
- Informative bars that close after a primary candle are not visible to that primary row.

---

### Scenario 4: Session VP live-parity mode uses expanding current-session profile
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given session VP indicators (`vp_poc`, `vp_vah`, `vp_val`)
  When  they are computed in live-parity mode
  Then  row `t` uses a profile built from the current session's bars from session open through `t`
  And   no later bars in the same session influence row `t`

**Chosen definition:**
| Definition | Meaning | Live parity |
|---|---|---|
| Expanding current session | Profile over session bars from session open through current bar | Yes |

**Rejected definition:**
| Definition | Why rejected |
|---|---|
| Completed current session broadcast to all bars in that session | Leaks future bars into earlier rows |

**Verify:**
```python
for i in session_indices:
    prefix = session_bars.loc[: session_bars.index[i]]
    expected = compute_session_volume_profile(prefix)
    got = live_parity_vp.iloc[i]
    assert got["vp_poc"] == expected.poc
    assert got["vp_vah"] == expected.vah
    assert got["vp_val"] == expected.val
```

**Also test:**
- The first bar of a session computes from a one-bar profile.
- A later bar in the same session changes the profile for that later bar only; earlier emitted rows are not mutated.

---

### Scenario 5: Windowed streaming fallback preserves real timestamps for session-sensitive indicators
**Priority:** Must
**Slice:** 1

**Gherkin:**
  Given bars with real timestamps spanning a calendar-date boundary
  When  `WindowedIndicatorState` converts its buffer to a DataFrame
  Then  the DataFrame index preserves the real bar timestamps
  And   session/date-sensitive handlers see the real date boundary
  And   no fabricated `2024-01-01` index is used

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| `df.index[0] == pd.Timestamp(bar["timestamp"], unit="s", tz="UTC")` for int-second timestamps | Inspect frame from helper / public test seam |
| `df.index.date` changes when input timestamps cross midnight | Feed bars across midnight |
| missing timestamps fail clearly for session-sensitive indicators | Assert `ValueError` or explicit unsupported result |

**Verify:**
```python
bars = [
    {"timestamp": 1781566200, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
    {"timestamp": 1781652600, "open": 2, "high": 3, "low": 2, "close": 3, "volume": 11},
]
state = WindowedIndicatorState(name="vp_poc", maxlen=10)
for bar in bars:
    state.update(bar)
frame = state._to_dataframe()  # or public test seam if introduced
assert str(frame.index[0].date()) != "2024-01-01"
assert frame.index[0].date() != frame.index[1].date()
```

**Also test:**
- ISO string timestamps.
- Python `datetime` timestamps.
- Numeric millisecond timestamps if supported; otherwise document that strategy-runtime expects seconds or ISO.

---

### Scenario 6: Existing full-frame batch mode is labelled non-live-parity for frame-dependent indicators
**Priority:** Should
**Slice:** 1

**Gherkin:**
  Given a user runs a backtest with legacy full-frame enrichment and a strategy requiring frame-dependent VP/AMT indicators
  When  the backtest starts
  Then  the system warns or records metadata that the result is not live-parity safe

**Expected output / state change:**
| Assertion | How to verify |
|---|---|
| Backtest result metadata includes `enrichment_mode="batch_full_frame"` | Inspect result |
| Backtest result metadata includes `live_parity_safe=False` for frame-dependent indicators | Inspect result |
| User-facing warning identifies `vp_poc/vp_vah/vp_val` as frame-dependent | Capture logger/result warning |
