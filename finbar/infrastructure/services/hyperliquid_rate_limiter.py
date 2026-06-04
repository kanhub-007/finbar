"""Token-bucket rate limiter for Hyperliquid API.
Hyperliquid uses a weight-based system (1200 weight/min) with per-endpoint
weight costs. This is a token bucket, fundamentally different from yfinance's
sliding window.

Features:
- Continuous weight replenishment (20 weight/sec)
- 80% safety margin to avoid edge cases
- Exponential backoff with jitter on 429 errors
- Progress logging every 100 requests
"""

from __future__ import annotations

import logging
import random
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
    """Token bucket rate limiter for Hyperliquid API."""

    def __init__(
        self,
        requests_per_minute: int = RATE_LIMIT_RPM,
        max_weight: int = RATE_LIMIT_WEIGHT,
        safety_margin: float = 0.8,
    ):
        self.max_weight = int(max_weight * safety_margin)  # 960
        self.replenish_rate = max_weight / 60.0  # 20 weight/sec
        self.min_interval = 60.0 / requests_per_minute

        self.current_weight = 0.0
        self.last_update = time.monotonic()
        self.last_request_time = 0.0

        self.total_requests = 0
        self.total_weight_used = 0
        self.consecutive_429_errors = 0
        self.backoff_until = 0.0

    def wait(self, weight: int = 20) -> None:
        """Wait until the token bucket has enough capacity for `weight`.

        Blocks the calling thread with time.sleep(). NOTE: this blocks
        the asyncio event loop when called from an async context. For
        Hyperliquid's generous limits (20 weight/sec refill), blocking
        is brief (~2 sec max per chunk). Use asyncio.to_thread() for
        long-running fetches if needed.

        Args:
            weight: Request weight (from Hyperliquid rate limit docs).
        """
        current_time = time.monotonic()

        # Check backoff from previous 429 errors
        if current_time < self.backoff_until:
            sleep_time = self.backoff_until - current_time
            logger.debug("Rate limiter: in backoff, sleeping %.1fs", sleep_time)
            time.sleep(sleep_time)
            current_time = time.monotonic()

        # Replenish weight based on time elapsed
        elapsed = current_time - self.last_update
        self.current_weight = max(
            0, self.current_weight - (elapsed * self.replenish_rate)
        )
        self.last_update = current_time

        # Wait until we have enough capacity
        while self.current_weight + weight > self.max_weight:
            needed = (self.current_weight + weight) - self.max_weight
            wait_time = needed / self.replenish_rate
            logger.debug("Rate limiter: waiting %.2fs for %d weight", wait_time, weight)
            time.sleep(wait_time)

            current_time = time.monotonic()
            elapsed = current_time - self.last_update
            self.current_weight = max(
                0, self.current_weight - (elapsed * self.replenish_rate)
            )
            self.last_update = current_time

        # Minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_interval:
            time.sleep(self.min_interval - time_since_last)

        # Consume weight
        self.current_weight += weight
        self.last_request_time = time.monotonic()
        self.total_requests += 1
        self.total_weight_used += weight

        if self.total_requests % 100 == 0:
            utilization = (self.current_weight / self.max_weight) * 100
            logger.info(
                "Rate limiter: %d requests, weight %.0f/%d (%.1f%%), 429s: %d",
                self.total_requests,
                self.current_weight,
                self.max_weight,
                utilization,
                self.consecutive_429_errors,
            )

    def on_rate_limit_error(self) -> None:
        """Called on HTTP 429. Applies exponential backoff with jitter."""
        self.consecutive_429_errors += 1
        base_backoff = min(2.0**self.consecutive_429_errors, 60.0)
        jitter = random.uniform(0, base_backoff * 0.25)
        backoff = base_backoff + jitter
        self.backoff_until = time.monotonic() + backoff
        logger.warning(
            "Rate limiter: 429 #%d, backoff %.1fs (base %.1fs + jitter %.1fs)",
            self.consecutive_429_errors,
            backoff,
            base_backoff,
            jitter,
        )

    def on_success(self) -> None:
        """Reset error counter after successful request."""
        if self.consecutive_429_errors > 0:
            logger.info(
                "Rate limiter: reset after %d errors",
                self.consecutive_429_errors,
            )
            self.consecutive_429_errors = 0
            self.backoff_until = 0.0

    def get_stats(self) -> dict[str, Any]:
        """Return current rate limiter statistics."""
        utilization = (
            (self.current_weight / self.max_weight) * 100 if self.max_weight > 0 else 0
        )
        return {
            "total_requests": self.total_requests,
            "total_weight_used": self.total_weight_used,
            "current_weight": f"{self.current_weight:.1f}/{self.max_weight}",
            "utilization": f"{utilization:.1f}%",
            "consecutive_429_errors": self.consecutive_429_errors,
        }
