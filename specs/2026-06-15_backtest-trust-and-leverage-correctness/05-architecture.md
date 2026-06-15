# ADR-1: Backtest engine owns warmup state progression

**Context:**
Warmup rows are currently sliced before the engine runs. This prevents crossover state from being built on warmup bars and can miss first-tradable crossover signals.

**Decision:**
The backtest engine will receive warmup metadata and own bar-by-bar state progression for all bars. Warmup bars may update strategy state, but trade creation/execution is gated until the first tradable bar.

**Consequences:**
- Live and backtest state progression become more consistent.
- The engine has one clear place for trade gating.
- The loop needs an explicit tradability check, but avoids pre-feeding state outside the engine.

---

# ADR-2: Maintenance-aware liquidation uses an explicit documented model

**Context:**
The existing leveraged liquidation formula ignores `maintenance_margin_pct`, even though the setting exists. Real exchange formulas vary by venue and margin mode.

**Decision:**
Implement a documented isolated-margin approximation using leverage and maintenance margin. Preserve zero-maintenance behaviour when `maintenance_margin_pct == 0.0`. Disclose the liquidation model in trust diagnostics.

**Consequences:**
- Leveraged results become more conservative and internally consistent.
- Results are still not venue-exact; diagnostics must say so.
- Future exchange-specific models can be added as strategies/calculators without changing the backtest loop.

---

# ADR-3: Risk price basis is configurable for backwards compatibility

**Context:**
Runtime strategies calculate stop/target from the signal bar close, while the backtest engine fills entries at the next bar open. Recalculating from fill is often more realistic, but changing the default would alter existing results.

**Decision:**
Add an explicit `risk_price_basis` execution setting. Default remains `signal_close`. New `entry_fill` mode recalculates stop/target from the actual entry fill before position sizing and validation.

**Consequences:**
- Existing result snapshots remain stable by default.
- Users can opt into more realistic fill-anchored risk.
- Trust diagnostics can explain which basis was used.

---

# ADR-4: Backtest trust diagnostics are part of the public contract

**Context:**
Backtest results can be mathematically correct under their assumptions but misleading if those assumptions are hidden.

**Decision:**
Trust diagnostics must disclose execution model assumptions: entry/exit model, gap handling, costs, leverage, margin mode, maintenance margin, liquidation model, warmup policy, risk price basis, borrow basis, and funding schedule.

**Consequences:**
- Users can evaluate whether a result is suitable for their trading context.
- Future model changes become visible in result payloads.
- Tests should assert diagnostics for trust-critical assumptions, not private implementation details.
