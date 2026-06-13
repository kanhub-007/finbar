"""Thread-safety and behaviour tests for rate limiters.

Regression: ``on_rate_limit_error`` previously mutated
``_rate_limit_backoff`` without holding the lock, while ``wait`` read it
under the lock from another thread. The write is now lock-guarded.
"""

from finbar.infrastructure.services.coinglass_rate_limiter import (
    CoinGlassRateLimiter,
)
from finbar.infrastructure.services.rate_limiter import YahooFinanceRateLimiter


def test_yfinance_on_rate_limit_sets_backoff_under_lock():
    limiter = YahooFinanceRateLimiter(base_backoff=2.0)
    backoff = limiter.on_rate_limit_error(attempt=0)
    assert backoff == 2.0
    # The field is written under the lock and is observable afterwards.
    assert limiter._rate_limit_backoff == 2.0


def test_coinglass_on_rate_limit_sets_backoff_under_lock():
    limiter = CoinGlassRateLimiter(base_backoff=2.0)
    backoff = limiter.on_rate_limit_error(attempt=2)
    assert backoff == 2.0 * (2 ** 2)
    assert limiter._rate_limit_backoff == 8.0


def test_yfinance_wait_consumes_backoff(monkeypatch):
    """wait() must clear the backoff flag set by on_rate_limit_error."""
    limiter = YahooFinanceRateLimiter(
        requests_per_second=1000, requests_per_minute=1000
    )
    limiter.on_rate_limit_error(attempt=0)
    assert limiter._rate_limit_backoff > 0

    monkeypatch.setattr(
        "finbar.infrastructure.services.rate_limiter.time.sleep",
        lambda s: None,
    )
    limiter.wait()
    # The backoff must have been consumed (cleared) after wait returns.
    assert limiter._rate_limit_backoff == 0.0
