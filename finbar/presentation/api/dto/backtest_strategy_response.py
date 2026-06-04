"""Metadata for a single backtest strategy."""

from pydantic import BaseModel


class BacktestStrategyResponse(BaseModel):
    name: str
    description: str
    required_indicators: list[str]
    default_params: dict
