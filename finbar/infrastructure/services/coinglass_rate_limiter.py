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
        self.min_interval = (
            1.0 / requests_per_second if requests_per_second > 0 else 0.0
        )
        self.max_per_minute = requests_per_minute
        self.max_retries = max_retries
        self.base_backoff = base_backoff

        self._last_request_time = 0.0
        self._request_times: deque[float] = deque(maxlen=1000)
        self._lock = threading.Lock()
        # Absolute deadline until which all callers must pause (set on 429).
        # Stored as an absolute timestamp so every concurrent caller observes
        # the same deadline and can sleep in parallel instead of convoying on
        # the lock for the full backoff duration.
        self._backoff_until = 0.0

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

        Thread‑safe. The potentially-long backoff sleep happens OUTSIDE the
        lock so concurrent callers pause in parallel instead of convoying.
        Admission control (spacing + minute window) and request recording
        stay atomic under the lock.
        """
        # --- Backoff phase: read the deadline, release the lock, sleep. ---
        # Loop/re-check so that if another thread extends the deadline
        # while we sleep, we do NOT proceed before the new deadline.
        while True:
            with self._lock:
                backoff_remaining = self._backoff_until - time.time()
            if backoff_remaining <= 0:
                break
            logger.debug(
                "CoinGlass rate limit backoff: sleeping %.1fs", backoff_remaining
            )
            time.sleep(backoff_remaining)

        # --- Admission phase: serialise spacing + minute window + record. ---
        # Any required wait is computed inside the lock (against a consistent
        # snapshot) but the sleep itself happens OUTSIDE it. On wake we
        # re-acquire the lock and re-check, because another caller may have
        # consumed capacity while we slept.
        while True:
            with self._lock:
                now = time.time()

                # -- Clear stale entries from the sliding window. --
                minute_ago = now - 60
                while self._request_times and self._request_times[0] < minute_ago:
                    self._request_times.popleft()

                # -- Enforce per-second spacing. --
                elapsed = now - self._last_request_time
                if self.min_interval > 0 and elapsed < self.min_interval:
                    wait_time = self.min_interval - elapsed
                elif len(self._request_times) >= self.max_per_minute:
                    oldest = self._request_times[0]
                    wait_time = max(0.0, 60 - (now - oldest))
                else:
                    # Admission granted: consume and record atomically.
                    self._last_request_time = now
                    self._request_times.append(now)
                    return

            # Sleep OUTSIDE the lock so concurrent callers pause in parallel
            # instead of convoying on the mutex for the full wait duration.
            logger.debug("CoinGlass rate limit: sleeping %.3fs", wait_time)
            time.sleep(wait_time)

    def on_rate_limit_error(self, attempt: int = 0) -> float:
        """Called on HTTP 429 — applies exponential backoff."""
        backoff = self.base_backoff * (2 ** min(attempt, 10))
        with self._lock:
            self._backoff_until = time.time() + backoff
        logger.warning(
            "CoinGlass rate limited! Backoff %.1fs (attempt %d)",
            backoff,
            attempt,
        )
        return backoff

    def reset(self) -> None:
        """Reset limiter state (useful after errors)."""
        with self._lock:
            self._request_times.clear()
            self._last_request_time = 0.0
            self._backoff_until = 0.0
