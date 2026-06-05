"""JsonRiskPriceCalculator — calculate risk prices for v2 JSON strategies."""

from finbar.core.domain.entities.risk_spec import RiskSpec
from finbar.core.domain.interfaces.risk_price_calculator import RiskPriceCalculator


class JsonRiskPriceCalculator(RiskPriceCalculator):
    """Calculate stop-loss and take-profit prices from RiskSpec settings."""

    def calculate(
        self,
        risk: RiskSpec | None,
        bar: dict,
        side: str,
    ) -> tuple[float, float]:
        """Return rounded stop and target prices for an entry signal."""
        if risk is None:
            return 0.0, 0.0
        close = float(bar.get("close", 0) or 0)
        stop = _stop_price(risk, bar, close, side)
        target = _target_price(risk, bar, close, side, stop)
        return round(stop, 2), round(target, 2)


def _stop_price(risk: RiskSpec, bar: dict, close: float, side: str) -> float:
    if risk.stop_loss_type == "atr":
        return _atr_stop(risk, bar, close, side)
    if risk.stop_loss_type == "fixed_pct" and risk.stop_pct > 0:
        return (
            close * (1 - risk.stop_pct)
            if side == "long"
            else close * (1 + risk.stop_pct)
        )
    return 0.0


def _target_price(
    risk: RiskSpec,
    bar: dict,
    close: float,
    side: str,
    stop: float,
) -> float:
    if risk.take_profit_type == "risk_reward" and stop > 0:
        distance = abs(close - stop) * risk.risk_reward_ratio
        return close + distance if side == "long" else close - distance
    if risk.take_profit_type == "atr":
        return _atr_target(risk, bar, close, side)
    if risk.take_profit_type == "fixed_pct" and risk.take_profit_pct > 0:
        return (
            close * (1 + risk.take_profit_pct)
            if side == "long"
            else close * (1 - risk.take_profit_pct)
        )
    return 0.0


def _atr_stop(risk: RiskSpec, bar: dict, close: float, side: str) -> float:
    atr = float(bar.get(risk.stop_indicator, 0) or 0)
    if atr <= 0 or risk.stop_multiplier <= 0:
        return 0.0
    return (
        close - atr * risk.stop_multiplier
        if side == "long"
        else close + atr * risk.stop_multiplier
    )


def _atr_target(risk: RiskSpec, bar: dict, close: float, side: str) -> float:
    atr = float(bar.get(risk.take_profit_indicator, 0) or 0)
    if atr <= 0 or risk.take_profit_multiplier <= 0:
        return 0.0
    return (
        close + atr * risk.take_profit_multiplier
        if side == "long"
        else close - atr * risk.take_profit_multiplier
    )
