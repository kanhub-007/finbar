"""BacktestRequest DTO — input for the run backtest use case."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BacktestRequest:
    """Request to run a backtest with a named strategy against historical bars.

    bars: list of OHLCV dicts (optionally enriched with indicators).
    strategy_name: name of the strategy to run (e.g. "sma_crossover").
    params: dict of strategy parameters (e.g. {"fast_period": 20}).
    initial_cash: starting capital for the backtest.
    """

    bars: list[dict]
    """OHLCV bars. Each dict must have: open, high, low, close, volume.
    May also include indicator columns from apply_indicators."""

    strategy_name: str
    """Strategy identifier, e.g. "sma_crossover", "rsi_mean_reversion"."""

    symbol: str = ""
    """Ticker symbol being backtested."""

    interval: str = ""
    """Bar interval (e.g. "1d", "1h", "5min")."""

    params: dict = field(default_factory=dict)
    """Strategy parameters forwarded to the strategy."""

    initial_cash: float = 10000.0
    """Starting capital."""

    leverage: float = 1.0
    """Leverage multiplier. 1.0 = spot."""

    risk_mode: str = "fixed_equity_risk"
    """Risk sizing mode: fixed_equity_risk or leverage_scaled_risk."""

    commission_pct: float = 0.0
    """Percentage commission per side, expressed as a decimal."""

    slippage_pct: float = 0.0
    """Directional slippage percentage, expressed as a decimal."""

    cap_explicit_size: bool = True
    """Cap explicit strategy sizes to buying power when true."""

    reject_oversized_explicit_orders: bool = False
    """Reject oversized explicit orders instead of capping them."""

    allow_negative_cash: bool = False
    """Allow backtests to overdraw cash when true."""

    market_calendar: str = "equity_regular_hours"
    """Market calendar used by annualization assumptions."""
