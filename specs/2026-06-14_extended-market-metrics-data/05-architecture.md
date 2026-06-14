# ADR-1: Metric capability registry before metric expansion

**Context:**
The strategy/theory documents include actual microstructure metrics and daily proxies. Some are computable from current OHLCV data; others require trades, quotes, Level 2 books, order-book events, external sentiment/options data, or multi-venue data.

**Decision:**
Add a market metric capability registry before adding many calculators. Every metric has an explicit data requirement, confidence classification (`actual`, `proxy`, `approximation`, `unavailable`), and proxy candidates.

**Consequences:**
- Users get clear diagnostics instead of silent bad approximations.
- Strategy validation can fail early when data is insufficient.
- Future providers can be added without changing metric semantics.

---

# ADR-2: Do not compute actual order-flow metrics from OHLCV-only data

**Context:**
Metrics like effective spread, Lee-Ready signed flow, Kyle lambda, Cont-Kukanov OFI, absorption, iceberg detection, resiliency, and information share are not identifiable from OHLCV bars alone.

**Decision:**
OHLCV-only Finbar may compute labelled proxies only. Actual tick/quote/L2 metrics require new provider interfaces and data storage before being marked computable.

**Consequences:**
- Backtests remain honest about data limitations.
- OHLCV proxy strategies can still be researched.
- More advanced order-flow work becomes a separate data-provider feature.

---

# ADR-3: Metric calculators use Strategy pattern by metric family

**Context:**
The metric list spans spread, volatility, liquidity, order flow, profile, price action, sentiment, derivatives, and portfolio metrics.

**Decision:**
Use a `MetricCalculatorStrategy` interface. Each family has its own calculator. A composite market metric calculator dispatches by catalog definition.

**Consequences:**
- Avoids a god indicator calculator.
- Supports optional dependencies and provider-backed metrics.
- Keeps each calculator testable with black-box fixtures.

---

# ADR-4: External provider data remains infrastructure

**Context:**
Some metrics require VIX/options/COT/social sentiment/derivatives providers. Provider APIs and SDKs are external systems.

**Decision:**
Domain defines provider interfaces and DTOs. Infrastructure implements adapters and maps provider payloads to domain entities. No provider SDK objects cross into domain/application.

**Consequences:**
- Clean Architecture remains intact.
- Tests can use in-memory fake providers.
- Missing providers produce explicit capability diagnostics.

---

# ADR-5: Price-action theory outputs are labelled approximations

**Context:**
Fibonacci, supply/demand zones, SMC, VSA, Wyckoff, and Bill Williams indicators can be approximated with OHLCV, but their discretionary interpretation can overstate certainty.

**Decision:**
Expose deterministic, documented heuristics only. Capability metadata must label them as OHLCV approximations and disclose lookback/threshold assumptions.

**Consequences:**
- Strategies can use reproducible columns.
- Users are warned that columns are not proof of hidden institutional orders or true order-flow events.
- Live/replay can avoid look-ahead bias through closed-bar emission rules.
