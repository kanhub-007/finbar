"""Annualization factor lookup for metric computation.

Pure domain logic — no pandas, no infrastructure dependencies.
Used by BacktestResultBuilder and portfolio analytics.
"""


def annualization_factor(interval: str, market_calendar: str) -> tuple[float, str]:
    """Return approximate periods per year and warning for an interval."""
    normalized = interval.lower().strip()
    calendar = (market_calendar or "equity_regular_hours").lower().strip()
    factors = _calendar_factors(calendar)
    if normalized in factors:
        return factors[normalized], ""
    if not normalized:
        return (
            factors["1d"],
            "No interval supplied; annualized metrics use 1d bars.",
        )
    return (
        factors["1d"],
        "Unknown interval; annualized metrics use 1d "
        f"{calendar} calendar assumption.",
    )


def _calendar_factors(market_calendar: str) -> dict[str, float]:
    """Return annualization factors for a supported market calendar."""
    if market_calendar == "crypto_24_7":
        return _crypto_24_7_factors()
    return _equity_regular_hours_factors()


def _equity_regular_hours_factors() -> dict[str, float]:
    """Return periods/year for regular-hours equity bars."""
    return {
        "1d": 252.0,
        "1w": 52.0,
        "1h": 252.0 * 6.5,
        "1m": 252.0 * 390.0,
        "1min": 252.0 * 390.0,
        "5m": 252.0 * 78.0,
        "5min": 252.0 * 78.0,
        "15m": 252.0 * 26.0,
        "15min": 252.0 * 26.0,
        "30m": 252.0 * 13.0,
        "30min": 252.0 * 13.0,
        "4h": 252.0 * 1.625,
    }


def _crypto_24_7_factors() -> dict[str, float]:
    """Return periods/year for continuously traded crypto bars."""
    return {
        "1d": 365.0,
        "1w": 365.0 / 7.0,
        "1h": 365.0 * 24.0,
        "1m": 365.0 * 24.0 * 60.0,
        "1min": 365.0 * 24.0 * 60.0,
        "5m": 365.0 * 24.0 * 12.0,
        "5min": 365.0 * 24.0 * 12.0,
        "15m": 365.0 * 24.0 * 4.0,
        "15min": 365.0 * 24.0 * 4.0,
        "30m": 365.0 * 24.0 * 2.0,
        "30min": 365.0 * 24.0 * 2.0,
        "4h": 365.0 * 6.0,
    }
