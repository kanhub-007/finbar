"""BacktestInputValidator — validates bars before backtest execution.

Strictness contract (spec 2026-06-23): backtests must never run on bars
that lack a parseable ``timestamp``, because the engine derives dates,
calendar analytics, and annualization from the DataFrame index. A missing
timestamp would otherwise fall back to a row-number index and silently
produce fake dates.
"""

from __future__ import annotations

from typing import Protocol

from finbar.core.domain.entities.backtest_input_validation_result import (
    BacktestInputValidationResult,
)


class BacktestInputValidator(Protocol):
    """Validate backtest bar dicts before execution."""

    def validate(
        self,
        bars: list[dict],
        interval: str = "",
    ) -> BacktestInputValidationResult:
        """Return a validation result; never raise on ordinary bad input.

        Args:
            bars: OHLCV bar dicts (optionally enriched).
            interval: Bar interval string for interval-known checks.

        Returns:
            A :class:`BacktestInputValidationResult`. Callers surface
            ``errors`` as user-facing backtest errors.
        """
        ...


__all__ = ["BacktestInputValidator"]
