"""Request body for running a backtest."""

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    bars: list[dict] = Field(
        ...,
        description="List of OHLCV bar dicts (optionally enriched)",
    )
    strategy_name: str = Field(..., description="Strategy identifier")
    symbol: str = Field(default="", description="Ticker symbol")
    interval: str = Field(default="", description="Bar interval")
    params: dict = Field(default_factory=dict, description="Strategy parameters")
    initial_cash: float = Field(default=10000.0, description="Starting capital")
