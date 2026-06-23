"""DefaultBacktestInputValidator — pure validation of backtest bar dicts.

No I/O, no frameworks. Implements the :class:`BacktestInputValidator`
protocol. Timestamp checks happen here (before DataFrame conversion) so
bars without a timestamp never reach the engine with a fake row-number
index.
"""

from __future__ import annotations

from finbar.core.domain.entities.backtest_input_validation_result import (
    BacktestInputValidationResult,
)
from finbar.core.domain.services.annualization import annualization_factor

_TIMESTAMP_KEY = "timestamp"


class DefaultBacktestInputValidator:
    """Validates that backtest bars carry real timestamps."""

    def validate(
        self,
        bars: list[dict],
        interval: str = "",
    ) -> BacktestInputValidationResult:
        """Validate non-empty bars; empty bars are the caller's responsibility.

        Args:
            bars: OHLCV bar dicts (optionally enriched).
            interval: Bar interval string (e.g. ``"1d"``, ``"1h"``).

        Returns:
            A :class:`BacktestInputValidationResult`.
        """
        bar_count = len(bars)
        if bar_count == 0:
            return BacktestInputValidationResult(
                valid=True,
                errors=[],
                bar_count=0,
                has_timestamp=False,
                interval_known=False,
            )

        errors: list[str] = []
        has_timestamp = self._every_bar_has_timestamp(bars)
        if not has_timestamp:
            errors.append(
                "Backtest bars must include a parseable 'timestamp' field on "
                "every bar (int seconds, ISO-8601, or datetime). Without it "
                "the engine would derive dates from row numbers and corrupt "
                "calendar-based metrics."
            )

        interval_known = self._is_interval_known(interval)
        return BacktestInputValidationResult(
            valid=not errors,
            errors=errors,
            bar_count=bar_count,
            has_timestamp=has_timestamp,
            interval_known=interval_known,
        )

    @staticmethod
    def _every_bar_has_timestamp(bars: list[dict]) -> bool:
        """Return True when every bar has a non-empty timestamp value."""
        return all(bool(bar.get(_TIMESTAMP_KEY)) for bar in bars)

    @staticmethod
    def _is_interval_known(interval: str) -> bool:
        """Return True when the interval string is recognized for annualization.

        Uses the annualization helper's warning as the signal: any warning
        ("No interval supplied" / "Unknown interval") means the interval is
        not confidently known. Calendar-aware strictness is handled by the
        result builder (spec Scenario 9).
        """
        _factor, warning = annualization_factor(interval, "equity_regular_hours")
        return warning == ""


__all__ = ["DefaultBacktestInputValidator"]
