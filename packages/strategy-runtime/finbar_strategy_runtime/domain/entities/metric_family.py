"""MetricFamily — broad category a market metric belongs to."""

from enum import Enum


class MetricFamily(str, Enum):
    """Taxonomy grouping for market metrics."""

    SPREAD = "spread"
    VOLATILITY = "volatility"
    LIQUIDITY_IMPACT = "liquidity_impact"
    ORDER_FLOW = "order_flow"
    INFORMED_TRADING = "informed_trading"
    JUMP_TAIL_RISK = "jump_tail_risk"
    INTRADAY_SEASONALITY = "intraday_seasonality"
    ORDER_ARRIVAL = "order_arrival"
    RESILIENCY = "resiliency"
    INFORMATION_SHARE = "information_share"
    PRICE_ACTION = "price_action"
    TREND_STRUCTURE = "trend_structure"
    VSA = "vsa"
    SENTIMENT = "sentiment"
    DERIVATIVES = "derivatives"
    PORTFOLIO = "portfolio"
    CROSS_ASSET = "cross_asset"
