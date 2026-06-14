"""Derivatives pass-through handlers.

These handlers ensure pre-merged derivatives columns exist (Invariant #2).
The actual data comes from ``merge_derivatives_asof`` (called by the job
runner before ``calculate()``).
"""

import numpy as np
import pandas as pd

from finbar_strategy_runtime.indicators._handler_registry import _register
from finbar_strategy_runtime.indicators.derivatives_constants import (
    DERIVATIVES_FIELDS,
)


def _register_derivatives_handlers() -> None:
    """Register pass-through handlers for derivatives metrics."""

    def _make_handler(col_name: str):
        @_register(col_name)
        def _handler(df, _name, _cache):
            if col_name not in df.columns:
                df[col_name] = np.nan
            return df
        return _handler

    for name in DERIVATIVES_FIELDS:
        _make_handler(name)


_register_derivatives_handlers()
