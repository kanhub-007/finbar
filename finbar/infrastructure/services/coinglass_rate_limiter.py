"""CoinGlass rate limiter — sliding‑window with dynamic header‑based limits.

Follows the same pattern as YahooFinanceRateLimiter: thread‑safe,
sliding window, wait() blocks until capacity available. CoinGlass
additionally reads rate limits from response headers.
"""

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PER_MINUTE = 30
_DEFAULT_REQUESTS_PER_SECOND = 1.0


class CoinGlassRateLimiter:
    """Sliding‑window rate limiter with dynamic limits from API headers."""

    def __init__(
        self,
        requests_per_second: float = _DEFAULT_REQUESTS_PER_SECOND,
        requests_per_minute: int = _DEFAULT_MAX_PER_MINUTE,
        max_retries: int = 3,
        base_backoff: float = 2.0,
    ):
        self.min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self.max_per_minute = requests_per_minute
        self.max_retries = max_retries
        self.base_backoff = base_backoff

        self._last_request_time = 0.0
        self._request_times: deque[float] = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._rate_limit_backoff = 0.0

    def update_from_headers(self, headers: dict[str, str]) -> None:
        """Update dynamic limits from CoinGlass response headers."""
        for key, value in headers.items():
            if key.lower() == "api-key-max-limit":
                try:
                    self.max_per_minute = max(1, int(value))
                except (ValueError, TypeError):
                    pass

    def wait(self) -> None:
        """Block if necessary to respect rate limits.

        Thread‑safe — uses the same deque‑based sliding window pattern
        as YahooFinanceRateLimiter.
        """
        with self._lock:
            now = time.time()

            if self._rate_limit_backoff > 0:
                if now < self._last_request_time + self._rate_limit_backoff:
                    sleep_time = self._last_request_time + self._rate_limit_backoff - now
                    logger.debug("CoinGlass rate limit backoff: sleeping %.1fs", sleep_time)
                    time.sleep(sleep_time)
                    now = time.time()
                self._rate_limit_backoff = 0.0

            elapsed = now - self._last_request_time
            if self.min_interval > 0 and elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

            now = time.time()
            minute_ago = now - 60
            while self._request_times and self._request_times[0] < minute_ago:
                self._request_times.popleft()

            if len(self._request_times) >= self.max_per_minute:
                oldest = self._request_times[0]
                wait = 60 - (now - oldest)
                if wait > 0:
                    logger.debug("CoinGlass minute window full, sleeping %.1fs", wait)
                    time.sleep(wait)
                    now = time.time()
                    minute_ago = now - 60
                    while self._request_times and self._request_times[0] < minute_ago:
                        self._request_times.popleft()

            self._last_request_time = now
            self._request_times.append(now)

    def on_rate_limit_error(self, attempt: int = 0) -> float:
        """Called on HTTP 429 — applies exponential backoff."""
        backoff = self.base_backoff * (2 ** min(attempt, 10))
        self._rate_limit_backoff = backoff
        logger.warning("CoinGlass rate limited! Backoff %.1fs (attempt %d)", backoff, attempt)
        return backoff

    def reset(self) -> None:
        """Reset limiter state (useful after errors)."""
        with self._lock:
            self._request_times.clear()
            self._last_request_time = 0.0
            self._rate_limit_backoff = 0.0
