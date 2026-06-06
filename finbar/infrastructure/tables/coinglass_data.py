"""CoinGlassData — ORM table for derivatives market metrics."""

from sqlalchemy import Column, Float, String

from finbar.infrastructure.data.connection import Base


class CoinGlassData(Base):
    """Persisted derivatives metrics from CoinGlass API.

    Stores per‑timestamp funding rate, OI, CVD, and liquidation data.
    Crypto only — no stock equivalent.
    """

    __tablename__ = "coinglass_data"

    symbol = Column(String, primary_key=True, nullable=False)
    """Ticker symbol (e.g. BTC, ETH)."""

    timestamp = Column(String, primary_key=True, nullable=False)
    """ISO‑8601 timestamp of the data point."""

    interval = Column(String, nullable=False)
    """Bar interval (e.g. 1h, 4h, 1d)."""

    open_interest = Column(Float, nullable=True)
    """Total open interest in USD."""

    open_interest_delta_1h = Column(Float, nullable=True)
    """1‑hour OI change (USD)."""

    open_interest_delta_24h = Column(Float, nullable=True)
    """24‑hour OI change (USD)."""

    cumulative_volume_delta = Column(Float, nullable=True)
    """CVD — cumulative delta buyer vs seller volume."""

    funding_rate = Column(Float, nullable=True)
    """Current funding rate (per period)."""

    long_short_ratio = Column(Float, nullable=True)
    """Ratio of long to short positions."""

    liquidations_long_1h = Column(Float, nullable=True)
    """1‑hour long liquidations (USD)."""

    liquidations_short_1h = Column(Float, nullable=True)
    """1‑hour short liquidations (USD)."""

    liquidations_long_24h = Column(Float, nullable=True)
    """24‑hour long liquidations (USD)."""

    liquidations_short_24h = Column(Float, nullable=True)
    """24‑hour short liquidations (USD)."""
