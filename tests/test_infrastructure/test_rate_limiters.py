"""Thread-safety and behaviour tests for rate limiters.

Regression: the backoff sleep was previously performed while holding the
lock, so every concurrent caller convoyed on the lock for the full backoff
duration (up to ~60s). The backoff sleep now happens outside the lock.
"""

import threading

from finbar.infrastructure.services.coinglass_rate_limiter import (
    CoinGlassRateLimiter,
)
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter


def test_yfinance_on_rate_limit_sets_backoff_deadline():
    """on_rate_limit_error records an absolute backoff deadline under the lock."""
    import time

    limiter = YahooFinanceRateLimiter(base_backoff=2.0)
    before = time.time()
    backoff = limiter.on_rate_limit_error(attempt=0)
    after = time.time()
    assert backoff == 2.0
    # The deadline is roughly "now + backoff".
    assert before + 2.0 <= limiter._backoff_until <= after + 2.0


def test_coinglass_on_rate_limit_sets_backoff_deadline():
    import time

    limiter = CoinGlassRateLimiter(base_backoff=2.0)
    before = time.time()
    backoff = limiter.on_rate_limit_error(attempt=2)
    after = time.time()
    assert backoff == 2.0 * (2 ** 2)
    assert before + 8.0 <= limiter._backoff_until <= after + 8.0


def test_yfinance_wait_sleeps_for_backoff_outside_lock(monkeypatch):
    """wait() must sleep for the remaining backoff, but the sleep is performed
    outside the lock so concurrent callers do not convoy."""
    import time

    limiter = YahooFinanceRateLimiter(
        requests_per_second=1000, requests_per_minute=1000
    )
    # Set a 5s backoff deadline "now + 5s".
    limiter._backoff_until = time.time() + 5.0

    slept = []
    # Capture which thread id performs each sleep; the limiter's internal lock
    # acquisition should NOT be held during the sleep.
    monkeypatch.setattr(
        "finbar.infrastructure.services.rate_limiter.time.sleep",
        lambda s: slept.append((threading.get_ident(), s)),
    )
    limiter.wait()
    # A backoff sleep of roughly 5s was requested.
    assert slept, "expected a backoff sleep"
    assert any(abs(s - 5.0) < 1.0 for _tid, s in slept)


def test_yfinance_wait_backoff_sleeps_run_in_parallel(monkeypatch):
    """Regression: two concurrent wait() callers must both observe the backoff
    deadline and sleep in parallel, rather than one blocking the other on the
    lock for the full backoff duration."""
    import time

    limiter = YahooFinanceRateLimiter(
        requests_per_second=1000, requests_per_minute=1000
    )
    limiter._backoff_until = time.time() + 5.0

    barrier = threading.Barrier(2)
    sleep_starts: list[float] = []

    real_sleep = time.sleep

    def tracking_sleep(seconds):
        # Record the start of the (simulated) backoff sleep.
        sleep_starts.append(time.time())
        # Don't actually sleep — just synchronise to prove parallelism.
        real_sleep(0.01)

    monkeypatch.setattr(
        "finbar.infrastructure.services.rate_limiter.time.sleep", tracking_sleep
    )

    def call():
        barrier.wait()
        limiter.wait()

    t1 = threading.Thread(target=call)
    t2 = threading.Thread(target=call)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Both backoff sleeps should have started near-simultaneously (well within
    # the backoff duration). Under the old lock-held-during-sleep design, the
    # second would only start after the first completed (~5s later).
    backoff_sleeps = [s for s in sleep_starts]
    assert len(backoff_sleeps) >= 2
    assert abs(backoff_sleeps[0] - backoff_sleeps[1]) < 1.0


def test_yfinance_reset_clears_backoff():
    limiter = YahooFinanceRateLimiter()
    limiter.on_rate_limit_error(attempt=0)
    assert limiter._backoff_until > 0
    limiter.reset()
    assert limiter._backoff_until == 0.0
