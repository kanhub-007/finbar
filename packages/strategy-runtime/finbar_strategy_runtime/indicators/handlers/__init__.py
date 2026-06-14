"""Indicator handler modules — importing this package registers all handlers.

Each sub-module uses ``@_register`` to populate ``_INDICATOR_HANDLERS``.
Importing this package ensures every handler is registered before any
``calculate()`` or ``check()`` call.
"""

from finbar_strategy_runtime.indicators.handlers import (  # noqa: F401
    core_ta,
    inside_bar,
    trend_breakout,
    vwap_bands,
    volume_profile,
    profile_classifiers,
    market_profile_amt,
    microstructure,
    price_action,
    derivatives,
    intraday_realized,
)
