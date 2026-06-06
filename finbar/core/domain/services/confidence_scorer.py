"""ConfidenceScorer — pure domain algorithm for 0‑100 conviction scoring.

No pandas, no I/O. Takes individual indicator values and returns a
ConfidenceScore with full component breakdown.
"""

from finbar.core.domain.entities.confidence_score import ConfidenceScore
from finbar.core.domain.entities.risk_factor import RiskFactor


class ConfidenceScorer:
    """Score trading conviction from indicator values using an additive model.

    Based on H‑Stocks Smart Cache methodology, simplified for single‑TF
    (daily only) operation. All inputs are plain floats / strings — zero
    infrastructure dependencies.
    """

    def score(
        self,
        *,
        adx: float = 0.0,
        direction: str = "",
        mtf_status: str = "",
        breakout_status: str = "",
        rvol: float = 0.0,
        is_power_zone: bool = False,
        risk_factors: list[str] | None = None,
    ) -> ConfidenceScore:
        """Compute a confidence score from indicator snapshots.

        Args:
            adx: ADX-14 value.
            direction: Trend direction (BULLISH / BEARISH / NEUTRAL).
            mtf_status: Multi‑timeframe alignment (FULLY_ALIGNED etc.).
            breakout_status: Breakout state (CONFIRMED / TRIGGERED / NONE).
            rvol: Relative volume vs 20‑period SMA.
            is_power_zone: Whether the breakout level is a power zone.
            risk_factors: List of active risk factor strings.

        Returns:
            ConfidenceScore with final score and component breakdown.
        """
        risk_factors = risk_factors or []
        base = 35  # single‑TF (daily only)

        trend = self._trend_clarity(adx, direction)
        mtf = self._mtf_bonus(mtf_status)
        brk = self._breakout_bonus(breakout_status)
        vol = self._volume_bonus(rvol)
        pz = 4 if is_power_zone else 0

        penalty, reasons = self._compute_penalties(risk_factors)

        raw = base + trend + mtf + brk + vol + pz - penalty
        score = max(0, min(100, raw))

        return ConfidenceScore(
            score=score,
            base=base,
            trend_clarity=trend,
            mtf_alignment=mtf,
            breakout=brk,
            volume=vol,
            power_zone=pz,
            penalty=penalty,
            penalty_reasons=reasons,
        )

    # ── component helpers ────────────────────────────────────────────

    @staticmethod
    def _trend_clarity(adx: float, direction: str) -> int:
        if adx > 25 and direction and direction != "NEUTRAL":
            return 10
        return 0

    @staticmethod
    def _mtf_bonus(mtf_status: str) -> int:
        mapping = {
            "FULLY_ALIGNED": 15,
            "PARTIALLY_ALIGNED": 8,
            "NEUTRAL": 0,
            "MIXED": 0,
            "CONFLICTED": -8,
        }
        return mapping.get(mtf_status, 0)

    @staticmethod
    def _breakout_bonus(breakout_status: str) -> int:
        mapping = {
            "CONFIRMED": 10,
            "TRIGGERED": 4,
        }
        return mapping.get(breakout_status, 0)

    @staticmethod
    def _volume_bonus(rvol: float) -> int:
        if rvol >= 3.0:
            return 12
        if rvol >= 2.0:
            return 8
        if rvol >= 1.5:
            return 5
        return 0

    @staticmethod
    def _compute_penalties(risk_factors: list[str]) -> tuple[int, list[str]]:
        penalty = 0
        reasons: list[str] = []
        mapping = {
            "FAKEOUT_CRITICAL": (-15, "Critical fakeout risk"),
            "FAKEOUT_HIGH": (-8, "High fakeout risk"),
            RiskFactor.OVEREXTENDED_UP: (-4, "RSI extreme overbought"),
            RiskFactor.OVEREXTENDED_DOWN: (-4, "RSI extreme oversold"),
            RiskFactor.STALE_DATA: (-10, "Bar data is stale"),
        }
        for factor in risk_factors:
            if factor in mapping:
                p, reason = mapping[factor]
                penalty += abs(p)
                reasons.append(reason)
        return penalty, reasons
