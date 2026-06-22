# ADR-1: Incremental VP uses simple bin aggregation, not full re-sort
**Context:** Session VP (POC/VAH/VAL) recomputes on every bar by running the full
batch handler on the windowed frame. Within a session, 48 bars at 30min means 48
full batch calls per session. An incremental approach could use a sorted tree or
a simple dict of price→volume bins.

**Decision:** Use a simple `dict[float, volume]` with rounded price keys. On each
bar, add volume at (high+low+close)/3 rounded to nearest tick. Materialization
sorts keys once when a VP value is requested. Since sessions are typically 48 bars,
sorting 48 keys is negligible.

**Consequences:**
- ✅ Simple implementation, easy to verify correctness
- ✅ O(n_bins log n_bins) materialization, where n_bins ≈ bars_in_session
- ⚠️ If sessions grow very long (e.g. weekly), sort cost grows. Acceptable for now.

# ADR-2: Session-count window uses crypto 24/7 as default
**Context:** `_SESSION_COUNT_WINDOW` was 500 bars, designed for poc_slope_5 at 30min
with generous headroom. Different markets have different session lengths:
crypto = 24h, equity = 6.5h. The engine doesn't know the market calendar at init time.

**Decision:** Use crypto (48 bars/session at 30min, 24 at 1h) as the conservative
default. Equity sessions are shorter (13 bars at 30min), so a crypto-sized window
works for equity too (just slightly oversized). Market-calendar-aware window sizing
is left for a future improvement.

**Consequences:**
- ✅ Simple — one constant `_BARS_PER_SESSION = 48`
- ✅ Safe — crypto sizing is always >= equity sizing
- ⚠️ Equity backtests use slightly oversized windows (waste ~3.5x on window size)

# ADR-3: Thread-level parallelism, not process-level
**Context:** MTF enrichment runs primary and informative engines independently
until the per-bar merge step. Since each engine is CPU-bound (Python), threading
won't bypass the GIL for computation but will overlap I/O and allow progress on
one engine while another is blocked.

**Decision:** Use `concurrent.futures.ThreadPoolExecutor` for parallel enrichment.
The primary engine runs in the main thread; informative engines run in worker
threads. Each engine is self-contained (own deque, own DataFrame conversion).

**Consequences:**
- ✅ Simple — no IPC, no shared state
- ✅ Informative enrichment can progress while primary is computing
- ⚠️ GIL limits true CPU parallelism, but the engines spend significant time in
  pandas/numpy C extensions where the GIL is released
- ⚠️ Thread safety: engines must not share mutable state
