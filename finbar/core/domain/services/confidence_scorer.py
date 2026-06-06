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

    # ── Scoring constants ────────────────────────────────────────────

    BASE_SINGLE_TF: int = 35
    BASE_MULTI_TF: int = 45

    TREND_CLARITY_BONUS: int = 10
    TREND_ADX_THRESHOLD: float = 25.0

    MTF_FULLY_ALIGNED: int = 15
    MTF_PARTIALLY_ALIGNED: int = 8
    MTF_CONFLICTED: int = -8
    MTF_NEUTRAL_MIXED: int = 0

    BREAKOUT_CONFIRMED: int = 10
    BREAKOUT_TRIGGERED: int = 4

    VOLUME_EXCEPTIONAL: int = 12
    VOLUME_EXCEPTIONAL_THRESHOLD: float = 3.0
    VOLUME_STRONG: int = 8
    VOLUME_STRONG_THRESHOLD: float = 2.0
    VOLUME_CONFIRMED: int = 5
    VOLUME_CONFIRMED_THRESHOLD: float = 1.5

    POWER_ZONE_BONUS: int = 4

    PENALTY_FAKEOUT_CRITICAL: int = 15
    PENALTY_FAKEOUT_HIGH: int = 8
    PENALTY_OVEREXTENDED: int = 4
    PENALTY_STALE: int = 10

    SCORE_MIN: int = 0
    SCORE_MAX: int = 100

    # ── Public API ────────────────────────────────────────────────────

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
        """Compute a confidence score from indicator snapshots."""
        risk_factors = risk_factors or []

        trend = self._trend_clarity(adx, direction)
        mtf = self._mtf_bonus(mtf_status)
        brk = self._breakout_bonus(breakout_status)
        vol = self._volume_bonus(rvol)
        pz = self.POWER_ZONE_BONUS if is_power_zone else 0

        penalty, reasons = self._compute_penalties(risk_factors)

        raw = self.BASE_SINGLE_TF + trend + mtf + brk + vol + pz - penalty
        score = max(self.SCORE_MIN, min(self.SCORE_MAX, raw))

        return ConfidenceScore(
            score=score,
            base=self.BASE_SINGLE_TF,
            trend_clarity=trend,
            mtf_alignment=mtf,
            breakout=brk,
            volume=vol,
            power_zone=pz,
            penalty=penalty,
            penalty_reasons=reasons,
        )

    # ── component helpers ────────────────────────────────────────────

    def _trend_clarity(self, adx: float, direction: str) -> int:
        if adx > self.TREND_ADX_THRESHOLD and direction and direction != "NEUTRAL":
            return self.TREND_CLARITY_BONUS
        return 0

    def _mtf_bonus(self, mtf_status: str) -> int:
        mapping = {
            "FULLY_ALIGNED": self.MTF_FULLY_ALIGNED,
            "PARTIALLY_ALIGNED": self.MTF_PARTIALLY_ALIGNED,
            "NEUTRAL": self.MTF_NEUTRAL_MIXED,
            "MIXED": self.MTF_NEUTRAL_MIXED,
            "CONFLICTED": self.MTF_CONFLICTED,
        }
        return mapping.get(mtf_status, 0)

    def _breakout_bonus(self, breakout_status: str) -> int:
        mapping = {
            "CONFIRMED": self.BREAKOUT_CONFIRMED,
            "TRIGGERED": self.BREAKOUT_TRIGGERED,
        }
        return mapping.get(breakout_status, 0)

    def _volume_bonus(self, rvol: float) -> int:
        if rvol >= self.VOLUME_EXCEPTIONAL_THRESHOLD:
            return self.VOLUME_EXCEPTIONAL
        if rvol >= self.VOLUME_STRONG_THRESHOLD:
            return self.VOLUME_STRONG
        if rvol >= self.VOLUME_CONFIRMED_THRESHOLD:
            return self.VOLUME_CONFIRMED
        return 0

    def _compute_penalties(self, risk_factors: list[str]) -> tuple[int, list[str]]:
        penalty = 0
        reasons: list[str] = []
        mapping: dict[str, tuple[int, str]] = {
            RiskFactor.FAKEOUT_CRITICAL: (
                self.PENALTY_FAKEOUT_CRITICAL,
                "Critical fakeout risk",
            ),
            RiskFactor.FAKEOUT_HIGH: (
                self.PENALTY_FAKEOUT_HIGH,
                "High fakeout risk",
            ),
            RiskFactor.OVEREXTENDED_UP: (
                self.PENALTY_OVEREXTENDED,
                "RSI extreme overbought",
            ),
            RiskFactor.OVEREXTENDED_DOWN: (
                self.PENALTY_OVEREXTENDED,
                "RSI extreme oversold",
            ),
            RiskFactor.STALE_DATA: (
                self.PENALTY_STALE,
                "Bar data is stale",
            ),
        }
        for factor in risk_factors:
            entry = mapping.get(factor)
            if entry is not None:
                penalty += entry[0]
                reasons.append(entry[1])
        return penalty, reasons
