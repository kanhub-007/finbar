"""Auction Drive — multi-timeframe strategy based on Auction Market Theory.

Enter long when price breaks above the Initial Balance high with
bullish trend alignment, volume confirmation, and bar strength.
Enter short on mirror conditions.

Uses primary intraday bars (1h or 30min) for entries and daily bars
for trend context. Falls back to proxy indicators when enrichment data
is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.core.domain.services.proxy_indicator import (
    ib_proxy_high,
    ib_proxy_low,
    typical_price,
)
from finbar.core.domain.services.proxy_indicator import (
    ibs as calc_ibs,
)
from finbar.core.domain.services.proxy_indicator import (
    rvol as calc_rvol,
)

logger = logging.getLogger(__name__)

# Default parameters — configurable via __init__
_DEFAULT_PARAMS = {
    "sma_fast": 50,
    "sma_slow": 200,
    "min_body_pct": 0.3,
    "volatility_buffer_atr_mult": 0.1,
    "min_rvol": 1.0,
    "min_ibs_long": 0.5,
    "max_ibs_short": 0.5,
    "stop_atr_multiplier": 2.5,
    "profit_target_atr_multiplier": 1.5,
    "risk_per_trade": 0.02,
    "require_trend_confirmation": True,
    "use_volatility_buffer": True,
    "use_rvol_filter": True,
    "use_ibs_filter": True,
    "allow_short": False,
}


class AuctionDriveStrategy(TradingStrategy):
    """Auction Market Theory strategy with adaptive indicator resolution.

    Primary timeframe: 1h or 30min intraday bars.
    Informative timeframe: 1d bars for trend context.
    Falls back to proxy indicators when enrichment columns are missing.
    """

    def __init__(self, **params: Any):
        """Initialise with optional parameter overrides.

        Args:
            **params: Any of the 15 strategy parameters. Missing keys
                use defaults from _DEFAULT_PARAMS.
        """
        self._p = dict(_DEFAULT_PARAMS)
        self._p.update(params)

        # Rolling state for self-computed fallback indicators
        self._close_history: list[float] = []
        self._atr_rma: float = 0.0
        self._atr_count: int = 0
        self._volume_history: list[float] = []

    # ------------------------------------------------------------------
    # TradingStrategy interface
    # ------------------------------------------------------------------

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="auction_drive",
            variant=DataMode.REAL,
            description=(
                "Auction Market Theory — enter at Initial Balance breakouts "
                "with trend confirmation, volume, and bar strength. "
                "Multi-timeframe: intraday entries + daily trend context."
            ),
            required_indicators=[
                "atr",
                "vwap",
                "ibs",
                "rvol",
                "ib_high",
                "ib_low",
                f"sma_{self._p['sma_fast']}",
                f"sma_{self._p['sma_slow']}",
            ],
            params=dict(self._p),
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        """Evaluate one bar and return a trading signal.

        Resolves indicators with multi-timeframe awareness:
        - Trend SMAs: sma_50_1d → sma_50 → rolling proxy
        - ATR: atr_1d → atr → Wilder RMA proxy
        - VWAP: vwap → typical_price proxy
        - IB: ib_high/ib_low → Open ± (mult × ATR) proxy
        """
        o = bar.get("open")
        h = bar.get("high")
        l = bar.get("low")  # noqa: E741
        c = bar.get("close")
        v = bar.get("volume", 0) or 0

        if any(x is None for x in (o, h, l, c)):
            return SignalResult()

        self._update_rolling_state(c, h, l, v)
        ind = self._resolve_indicators(bar, o, h, l, c, v)

        pos_size = position.get("size", 0)

        # --- Exit check ---
        if pos_size != 0:
            return self._check_exit(c, h, l, ind["vwap"], pos_size, position)

        # --- Entry check ---
        return self._check_entry(o, c, ind, position)

    def on_reset(self) -> None:
        """Clear rolling state for a new backtest run."""
        self._close_history.clear()
        self._atr_rma = 0.0
        self._atr_count = 0
        self._volume_history.clear()

    # ------------------------------------------------------------------
    # Indicator resolution (multi-timeframe aware)
    # ------------------------------------------------------------------

    def _resolve_indicators(
        self, bar: dict, o: float, h: float, l: float, c: float, v: float  # noqa: E741
    ) -> dict:
        """Resolve indicators with fallback chain.

        Priority: daily merged column → primary enrichment → self-computed.
        """
        # ATR: daily → primary → Wilder RMA
        atr = self._resolve_float(bar, "atr_1d", "atr")
        if atr == 0.0:
            atr = self._current_atr(c)

        # Trend SMAs: daily → primary → rolling close mean
        sma_fast = self._resolve_float(
            bar,
            f"sma_{self._p['sma_fast']}_1d",
            f"sma_{self._p['sma_fast']}",
        )
        if sma_fast == 0.0:
            sma_fast = self._sma(self._p["sma_fast"])

        sma_slow = self._resolve_float(
            bar,
            f"sma_{self._p['sma_slow']}_1d",
            f"sma_{self._p['sma_slow']}",
        )
        if sma_slow == 0.0:
            sma_slow = self._sma(self._p["sma_slow"])

        # VWAP: primary enrichment → typical price proxy
        db_vwap = bar.get("vwap")
        vwap = float(db_vwap) if db_vwap is not None else typical_price(h, l, c)

        # IB: true IB → proxy (Open ± mult × ATR)
        mult = self._p["volatility_buffer_atr_mult"]
        db_ib_h = bar.get("ib_high")
        db_ib_l = bar.get("ib_low")
        ib_h = float(db_ib_h) if db_ib_h is not None else ib_proxy_high(o, atr, mult)
        ib_l = float(db_ib_l) if db_ib_l is not None else ib_proxy_low(o, atr, mult)

        # RVOL: enrichment → self-computed
        db_rvol = bar.get("rvol")
        if db_rvol is not None:
            current_rvol = float(db_rvol)
        else:
            avg_vol = (
                float(np.mean(self._volume_history))
                if len(self._volume_history) >= 20
                else v
            )
            current_rvol = calc_rvol(v, avg_vol)

        # IBS: enrichment → self-computed
        db_ibs = bar.get("ibs")
        current_ibs = float(db_ibs) if db_ibs is not None else calc_ibs(h, l, c)

        return {
            "atr": atr,
            "sma_fast": sma_fast,
            "sma_slow": sma_slow,
            "vwap": vwap,
            "ib_high": ib_h,
            "ib_low": ib_l,
            "rvol": current_rvol,
            "ibs": current_ibs,
        }

    @staticmethod
    def _resolve_float(bar: dict, *keys: str) -> float:
        """Return the first non-None, non-NaN float value for the given keys."""
        for key in keys:
            val = bar.get(key)
            if val is not None:
                try:
                    f = float(val)
                    if not (f != f):  # NaN check
                        return f
                except (TypeError, ValueError):
                    continue
        return 0.0

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        o: float,
        c: float,
        ind: dict,
        position: dict,
    ) -> SignalResult:
        atr = ind["atr"]
        sma_fast = ind["sma_fast"]
        sma_slow = ind["sma_slow"]
        vwap = ind["vwap"]
        ib_high = ind["ib_high"]
        ib_low = ind["ib_low"]
        rvol = ind["rvol"]
        ibs_val = ind["ibs"]

        body = c - o
        body_pct = (abs(body) / o) * 100 if o > 0 else 0
        trend_up = sma_fast > sma_slow
        trend_down = sma_fast < sma_slow

        # --- Long entry ---
        if body > 0 and c > vwap and body_pct >= self._p["min_body_pct"]:
            if self._p["require_trend_confirmation"] and not trend_up:
                pass  # fail trend check
            elif self._p["use_volatility_buffer"] and c <= ib_high:
                pass  # fail IB breakout
            elif self._p["use_rvol_filter"] and rvol < self._p["min_rvol"]:
                pass  # fail volume
            elif self._p["use_ibs_filter"] and ibs_val < self._p["min_ibs_long"]:
                pass  # fail bar strength
            else:
                stop = c - atr * self._p["stop_atr_multiplier"]
                target = c + atr * self._p["profit_target_atr_multiplier"]
                return SignalResult(
                    action="buy",
                    direction="long",
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    position_size=0,  # engine computes risk-based
                    confidence=min(rvol / 3.0, 1.0),
                    metadata={
                        "reason": "auction_drive_long",
                        "vwap": round(vwap, 2),
                        "ibs": round(ibs_val, 4),
                        "rvol": round(rvol, 2),
                    },
                )

        # --- Short entry ---
        if (
            self._p["allow_short"]
            and body < 0
            and c < vwap
            and body_pct >= self._p["min_body_pct"]
        ):
            if self._p["require_trend_confirmation"] and not trend_down:
                pass
            elif self._p["use_volatility_buffer"] and c >= ib_low:
                pass
            elif self._p["use_rvol_filter"] and rvol < self._p["min_rvol"]:
                pass
            elif self._p["use_ibs_filter"] and ibs_val > self._p["max_ibs_short"]:
                pass
            else:
                stop = c + atr * self._p["stop_atr_multiplier"]
                target = c - atr * self._p["profit_target_atr_multiplier"]
                return SignalResult(
                    action="sell",
                    direction="short",
                    stop_price=round(stop, 2),
                    target_price=round(target, 2),
                    position_size=0,  # engine computes risk-based
                    confidence=min(rvol / 3.0, 1.0),
                    metadata={
                        "reason": "auction_drive_short",
                        "vwap": round(vwap, 2),
                        "ibs": round(ibs_val, 4),
                        "rvol": round(rvol, 2),
                    },
                )

        return SignalResult(action="hold")

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        close: float,
        high: float,
        low: float,
        vwap: float,
        pos_size: int,
        position: dict,
    ) -> SignalResult:
        stop = position.get("stop_price", 0)
        target = position.get("target_price", 0)

        if pos_size > 0:  # Long
            if stop > 0 and low <= stop:
                return SignalResult(
                    action="sell",
                    direction="exit",
                    metadata={"reason": "stop_loss"},
                )
            if target > 0 and high >= target:
                return SignalResult(
                    action="sell",
                    direction="exit",
                    metadata={"reason": "profit_target"},
                )
            if close < vwap:
                return SignalResult(
                    action="sell",
                    direction="exit",
                    metadata={"reason": "vwap_cross"},
                )
        else:  # Short
            if stop > 0 and high >= stop:
                return SignalResult(
                    action="sell",
                    direction="exit",
                    metadata={"reason": "stop_loss"},
                )
            if target > 0 and low <= target:
                return SignalResult(
                    action="sell",
                    direction="exit",
                    metadata={"reason": "profit_target"},
                )
            if close > vwap:
                return SignalResult(
                    action="sell",
                    direction="exit",
                    metadata={"reason": "vwap_cross"},
                )

        return SignalResult(action="hold")

    # ------------------------------------------------------------------
    # Rolling fallback indicators
    # ------------------------------------------------------------------

    def _update_rolling_state(
        self, close: float, high: float, low: float, volume: float
    ) -> None:
        """Update rolling history for self-computed fallback indicators."""
        max_lookback = max(self._p["sma_slow"], 20, 14) + 1

        self._close_history.append(close)
        if len(self._close_history) > max_lookback:
            self._close_history = self._close_history[-max_lookback:]

        # True Range for Wilder RMA
        prev_close = self._close_history[-2] if len(self._close_history) >= 2 else close
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        self._atr_count += 1
        if self._atr_count <= 14:
            self._atr_rma = (
                self._atr_rma * (self._atr_count - 1) + tr
            ) / self._atr_count
        else:
            alpha = 1.0 / 14
            self._atr_rma = alpha * tr + (1 - alpha) * self._atr_rma

        self._volume_history.append(volume)
        if len(self._volume_history) > 20:
            self._volume_history = self._volume_history[-20:]

    def _current_atr(self, fallback_close: float) -> float:
        if self._atr_count >= 14:
            return self._atr_rma
        return fallback_close * 0.02

    def _sma(self, period: int) -> float:
        if len(self._close_history) >= period:
            return float(np.mean(self._close_history[-period:]))
        if self._close_history:
            return self._close_history[-1]
        return 0.0
