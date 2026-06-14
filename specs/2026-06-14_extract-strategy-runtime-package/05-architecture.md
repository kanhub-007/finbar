# ADR-1: Extract strategy runtime into a dedicated package

**Context:**
Finbar is the canonical strategy authoring/backtesting service. Finbot copied Finbar runtime files to evaluate the same strategies live. Copying preserves standalone operation but creates semantic drift risk.

**Decision:**
Create a dedicated package, `finbar-strategy-runtime`, imported as `finbar_strategy_runtime`. Finbar depends on this package for strategy parsing, validation, serialization, indicator enrichment, condition evaluation, risk calculation, and rule-based signal generation.

**Consequences:**
- Finbar and Finbot can share strategy semantics without code copying.
- Package APIs become a contract and require version discipline.
- Finbar keeps application-specific orchestration, persistence, fetchers, backtesting, optimization, REST/MCP, and startup wiring.

---

# ADR-2: Runtime package stops at signal generation

**Context:**
Finbar uses strategy output to backtest/optimize; Finbot uses it to plan and submit live orders. These intents differ.

**Decision:**
The package emits validation results, enriched bars, and `SignalResult`/strategy decisions only. It has no order model, exchange gateway, database, job manager, or network fetcher.

**Consequences:**
- The package is safe for both historical and live use.
- Finbot remains responsible for risk gates, idempotency, dry-run/testnet/live behaviour, and exchange submission.
- Finbar remains responsible for backtest execution assumptions, fills, slippage, fees, optimization, and persistence.

---

# ADR-3: Schema version is separate from package version

**Context:**
The strategy schema may remain `2.0` across multiple package releases, while the package may receive bug fixes and internal refactors.

**Decision:**
Keep `schema_version` in strategy definitions as a strategy contract version. Package semver describes library compatibility. Capability metadata must report both package version and supported schema versions.

**Consequences:**
- Finbot can reject unsupported schema versions clearly.
- Backwards-compatible runtime bug fixes do not require a strategy schema bump.
- Breaking strategy format changes require schema migration notes and compatibility tests.

---

# ADR-4: Finbar adapters remain in Finbar

**Context:**
Some current strategy workflows are embedded in Finbar use cases, artifacts, databases, REST/MCP tools, and fetch jobs.

**Decision:**
Only pure runtime and parser/enrichment/evaluation code moves into the package. Finbar adapters map package entities/results into Finbar DTOs, repositories, and tool responses.

**Consequences:**
- Clean Architecture dependency direction is preserved.
- Package remains small and publishable.
- Finbar may need temporary compatibility mappers during migration.
