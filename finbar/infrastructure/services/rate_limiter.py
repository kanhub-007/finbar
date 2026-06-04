"""Rate limiter for Yahoo Finance API requests.

Implements:
- Per-request minimum delay
- Sliding window request count limit
- Exponential backoff on rate limit errors (HTTP 429)
- Thread-safe operation
"""

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


class YahooFinanceRateLimiter:
    """Rate limiter for Yahoo Finance API requests."""

    def __init__(
        self,
        requests_per_second: float = 2.0,
        requests_per_minute: int = 60,
        max_retries: int = 3,
        base_backoff: float = 2.0,
    ):
        self.min_interval = 1.0 / requests_per_second
        self.max_per_minute = requests_per_minute
        self.max_retries = max_retries
        self.base_backoff = base_backoff

        self._last_request_time = 0.0
        self._request_times: deque[float] = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._rate_limit_backoff = 0.0

    def wait(self) -> None:
        """Wait if necessary to respect rate limits."""
        with self._lock:
            now = time.time()

            if self._rate_limit_backoff > 0:
                if now < self._last_request_time + self._rate_limit_backoff:
                    sleep_time = (
                        self._last_request_time + self._rate_limit_backoff - now
                    )
                    logger.debug("Rate limit backoff: sleeping %.1fs", sleep_time)
                    time.sleep(sleep_time)
                    now = time.time()
                self._rate_limit_backoff = 0.0

            elapsed_since_last = now - self._last_request_time
            if elapsed_since_last < self.min_interval:
                sleep_time = self.min_interval - elapsed_since_last
                logger.debug("Rate limit: sleeping %.3fs between requests", sleep_time)
                time.sleep(sleep_time)

            now = time.time()
            minute_ago = now - 60
            while self._request_times and self._request_times[0] < minute_ago:
                self._request_times.popleft()

            if len(self._request_times) >= self.max_per_minute:
                oldest = self._request_times[0]
                sleep_time = 60 - (now - oldest)
                if sleep_time > 0:
                    logger.debug(
                        "Rate limit: minute window full, sleeping %.1fs",
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    now = time.time()
                    minute_ago = now - 60
                    while self._request_times and self._request_times[0] < minute_ago:
                        self._request_times.popleft()

            self._last_request_time = now
            self._request_times.append(now)

    def on_rate_limit_error(self, attempt: int = 0) -> float:
        """Called when HTTP 429 is received.

        Returns backoff time in seconds.
        """
        backoff = self.base_backoff * (2 ** min(attempt, 10))
        self._rate_limit_backoff = backoff
        logger.warning(
            "Rate limited! Applying %ss backoff (attempt %d)", backoff, attempt
        )
        return backoff

    def reset(self) -> None:
        """Reset rate limiter state (useful after errors)."""
        with self._lock:
            self._request_times.clear()
            self._last_request_time = 0.0
            self._rate_limit_backoff = 0.0
