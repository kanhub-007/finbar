"""InformativeTimeframe entity for multi-timeframe strategies."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InformativeTimeframe:
    """A named non-primary timeframe used for contextual indicators.

    When ``symbol`` is set, bars are fetched for that symbol instead of
    the primary symbol.  This enables cross-asset signals — e.g. using
    BTC 1h data as a macro filter for SUI 30min entries.
    """

    alias: str
    """Strategy-local timeframe alias, e.g. daily."""

    interval: str
    """Concrete bar interval, e.g. 1d."""

    symbol: str = ""
    """Optional override symbol for this informative timeframe.
    When empty, the primary symbol is used."""
