"""Token-bucket rate limiter for Hyperliquid API.
Hyperliquid uses a weight-based system (1200 weight/min) with per-endpoint
weight costs. This is a token bucket, fundamentally different from yfinance's
sliding window.

Features:
- Continuous weight replenishment (20 weight/sec)
- 80% safety margin to avoid edge cases
- Exponential backoff with jitter on 429 errors
- Progress logging every 100 requests
- Thread-safe: the limiter is shared across concurrent fetch jobs, so all
  mutable state (current weight, timestamps, backoff deadline) is guarded by
  a lock. Long sleeps happen outside the lock so concurrent callers pause in
  parallel instead of convoying.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

RATE_LIMIT_RPM = 1000
RATE_LIMIT_WEIGHT = 1200

# Weight calculation per Hyperliquid docs:
#   candleSnapshot: base 20 + floor(candles / 60) per 60 candles
#   Other info requests (l2Book, allMids): weight 2
#   User role: weight 60
#   All other info requests: weight 20

CANDLE_WEIGHT_BASE = 20
DEFAULT_CANDLE_WEIGHT = 36  # For ~1000 candles (20 + 16)
TICKER_WEIGHT = 40  # meta + context calls (~20 weight each)


def calculate_candle_weight(num_candles: int = 1000) -> int:
    """Calculate weight for a candleSnapshot request.

    Weight = 20 (base) + floor(num_candles / 60).

    Examples:
    - 50 candles: 20 + 0 = 20 weight
    - 1000 candles: 20 + 16 = 36 weight
    - 5000 candles: 20 + 83 = 103 weight
    """
    return CANDLE_WEIGHT_BASE + (num_candles // 60)


class HyperliquidRateLimiter:
    """Token bucket rate limiter for Hyperliquid API.

    Thread-safe. A single limiter instance is shared by all concurrent fetch
    jobs (see service_factory._get_hl_fetcher), so admission control — weight
    replenishment, the capacity check, min-interval spacing, and consumption
    recording — is serialised under ``self._lock``. The potentially-long
    backoff and capacity-wait sleeps happen OUTSIDE the lock so concurrent
    callers pause in parallel instead of convoying on the lock.
    """

    def __init__(
        self,
        requests_per_minute: int = RATE_LIMIT_RPM,
        max_weight: int = RATE_LIMIT_WEIGHT,
        safety_margin: float = 0.8,
    ):
        self.max_weight = int(max_weight * safety_margin)  # 960
        self.replenish_rate = max_weight / 60.0  # 20 weight/sec
        self.min_interval = 60.0 / requests_per_minute

        # Mutable shared state — guarded by self._lock.
        self._current_weight = 0.0
        self._last_update = time.monotonic()
        self._last_request_time = 0.0
        self._consecutive_429_errors = 0
        self._backoff_until = 0.0

        # Counters read by get_stats(); also guarded by the lock so they are
        # never observed in a torn state mid-increment.
        self.total_requests = 0
        self.total_weight_used = 0

        self._lock = threading.Lock()

    def wait(self, weight: int = 20) -> None:
        """Wait until the token bucket has enough capacity for ``weight``.

        Thread-safe. The backoff sleep and the capacity-wait sleep happen
        OUTSIDE the lock (concurrent callers pause in parallel). Admission
        control — replenish, capacity check, min-interval spacing, and
        consumption — is atomic under the lock, so two callers can never both
        consume capacity that only one of them accounted for.

        Args:
            weight: Request weight (from Hyperliquid rate limit docs).
        """
        # --- Backoff phase: read the deadline, release the lock, sleep. ---
        # Loop/re-check so that if another thread extends the deadline while
        # we sleep, we do NOT proceed before the new deadline.
        while True:
            with self._lock:
                remaining = self._backoff_until - time.monotonic()
            if remaining <= 0:
                break
            logger.debug("Rate limiter: in backoff, sleeping %.1fs", remaining)
            time.sleep(remaining)

        # --- Admission phase: replenish + capacity/interval check. ---
        # Any required wait is computed inside the lock (against a consistent
        # snapshot of current_weight / last_request_time) but the sleep itself
        # happens outside it. On wake we re-acquire the lock and re-check,
        # because another caller may have consumed capacity while we slept.
        while True:
            with self._lock:
                now = time.monotonic()
                # Replenish weight based on time elapsed since last update.
                elapsed = now - self._last_update
                self._current_weight = max(
                    0.0, self._current_weight - (elapsed * self.replenish_rate)
                )
                self._last_update = now

                if self._current_weight + weight > self.max_weight:
                    # Not enough capacity: compute how long until enough weight
                    # replenishes, then sleep OUTSIDE the lock and re-check.
                    needed = (self._current_weight + weight) - self.max_weight
                    wait_time = needed / self.replenish_rate
                else:
                    # Enough capacity: enforce min-interval spacing, then consume.
                    time_since_last = now - self._last_request_time
                    if self.min_interval > 0 and time_since_last < self.min_interval:
                        wait_time = self.min_interval - time_since_last
                    else:
                        # Admission granted: consume and record atomically.
                        self._current_weight += weight
                        self._last_request_time = now
                        self.total_requests += 1
                        self.total_weight_used += weight
                        if self.total_requests % 100 == 0:
                            utilization = (self._current_weight / self.max_weight) * 100
                            logger.info(
                                "Rate limiter: %d requests, weight %.0f/%d "
                                "(%.1f%%), 429s: %d",
                                self.total_requests,
                                self._current_weight,
                                self.max_weight,
                                utilization,
                                self._consecutive_429_errors,
                            )
                        return
            logger.debug("Rate limiter: waiting %.2fs for %d weight", wait_time, weight)
            time.sleep(wait_time)

    def on_rate_limit_error(self) -> None:
        """Called on HTTP 429. Applies exponential backoff with jitter."""
        with self._lock:
            self._consecutive_429_errors += 1
            count = self._consecutive_429_errors
            base_backoff = min(2.0**count, 60.0)
            jitter = random.uniform(0, base_backoff * 0.25)
            backoff = base_backoff + jitter
            self._backoff_until = time.monotonic() + backoff
        logger.warning(
            "Rate limiter: 429 #%d, backoff %.1fs (base %.1fs + jitter %.1fs)",
            count,
            backoff,
            base_backoff,
            jitter,
        )

    def on_success(self) -> None:
        """Reset error counter after successful request."""
        with self._lock:
            if self._consecutive_429_errors > 0:
                logger.info(
                    "Rate limiter: reset after %d errors",
                    self._consecutive_429_errors,
                )
                self._consecutive_429_errors = 0
                self._backoff_until = 0.0

    def get_stats(self) -> dict[str, Any]:
        """Return current rate limiter statistics."""
        with self._lock:
            current_weight = self._current_weight
            total_requests = self.total_requests
            total_weight_used = self.total_weight_used
            consecutive = self._consecutive_429_errors
        utilization = (
            (current_weight / self.max_weight) * 100 if self.max_weight > 0 else 0
        )
        return {
            "total_requests": total_requests,
            "total_weight_used": total_weight_used,
            "current_weight": f"{current_weight:.1f}/{self.max_weight}",
            "utilization": f"{utilization:.1f}%",
            "consecutive_429_errors": consecutive,
        }
