"""DerivativesMetrics — provider‑agnostic derivatives market data.

Domain entity — not tied to CoinGlass or any specific data source.
Fields represent universal derivatives concepts that any provider
(CoinGlass, Velo, Laevitas) can supply.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DerivativesMetrics:
    """Per‑symbol derivatives market metrics at a point in time."""

    symbol: str = ""
    """Ticker symbol (e.g. BTC, ETH)."""

    timestamp: str = ""
    """ISO‑8601 timestamp of the data point."""

    open_interest: float | None = None
    """Total open interest in USD."""

    open_interest_delta_1h: float | None = None
    """1‑hour change in open interest (USD)."""

    open_interest_delta_24h: float | None = None
    """24‑hour change in open interest (USD)."""

    cumulative_volume_delta: float | None = None
    """CVD — cumulative delta between buyer and seller volume."""

    funding_rate: float | None = None
    """Current funding rate (per‑period, e.g. 8h for perps)."""

    funding_rate_annualised: float | None = None
    """Annualised funding rate (decimal, e.g. 0.10 = 10%)."""

    long_short_ratio: float | None = None
    """Ratio of long positions to short positions."""

    liquidations_long_1h: float | None = None
    """Long liquidations in the last hour (USD)."""

    liquidations_short_1h: float | None = None
    """Short liquidations in the last hour (USD)."""

    liquidations_long_24h: float | None = None
    """Long liquidations in the last 24 hours (USD)."""

    liquidations_short_24h: float | None = None
    """Short liquidations in the last 24 hours (USD)."""

    interval: str = ""
    """Bar interval this data aligns with (e.g. 1h, 1d)."""

    metadata: dict = field(default_factory=dict)
    """Provider‑specific metadata (e.g. exchange, contract type)."""
