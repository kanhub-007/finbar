"""Metric-value assertions for causal streaming parity tests."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def assert_equivalent_metric_value(
    got: Any,
    expected: Any,
    metric_name: str,
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-12,
) -> None:
    """Assert that two metric values are equivalent under metric semantics.

    Args:
        got: Value produced by the streaming path.
        expected: Value produced by the causal prefix oracle.
        metric_name: Metric name used in assertion diagnostics.
        rel_tol: Relative tolerance for numeric metrics.
        abs_tol: Absolute tolerance for numeric metrics.

    Raises:
        AssertionError: If the values are not equivalent.
    """
    if _both_missing(got, expected):
        return
    if _one_missing(got, expected):
        raise AssertionError(f"{metric_name}: got={got!r}, expected={expected!r}")
    if _is_bool_like(got) or _is_bool_like(expected):
        _assert_bool_equivalent(got, expected, metric_name)
        return
    if isinstance(got, str) or isinstance(expected, str):
        _assert_string_equivalent(got, expected, metric_name)
        return
    _assert_numeric_equivalent(got, expected, metric_name, rel_tol, abs_tol)


def _both_missing(left: Any, right: Any) -> bool:
    """Return True when both values are missing/NaN."""
    return _is_missing(left) and _is_missing(right)


def _one_missing(left: Any, right: Any) -> bool:
    """Return True when exactly one value is missing/NaN."""
    return _is_missing(left) != _is_missing(right)


def _is_missing(value: Any) -> bool:
    """Return True for None, pandas NA, and float NaN values."""
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except TypeError:
        return False
    if isinstance(missing, (bool, np.bool_)):
        return bool(missing)
    return False


def _is_bool_like(value: Any) -> bool:
    """Return True for Python/numpy boolean values."""
    return isinstance(value, (bool, np.bool_))


def _assert_bool_equivalent(got: Any, expected: Any, metric_name: str) -> None:
    """Assert bool values match without numeric coercion."""
    both_bool = _is_bool_like(got) and _is_bool_like(expected)
    if not (both_bool and bool(got) == bool(expected)):
        raise AssertionError(f"{metric_name}: got={got!r}, expected={expected!r}")


def _assert_string_equivalent(got: Any, expected: Any, metric_name: str) -> None:
    """Assert string classifier values match exactly."""
    if not (isinstance(got, str) and isinstance(expected, str) and got == expected):
        raise AssertionError(f"{metric_name}: got={got!r}, expected={expected!r}")


def _assert_numeric_equivalent(
    got: Any,
    expected: Any,
    metric_name: str,
    rel_tol: float,
    abs_tol: float,
) -> None:
    """Assert numeric metric values match within tolerance."""
    try:
        got_number = float(got)
        expected_number = float(expected)
    except (TypeError, ValueError) as exc:
        raise AssertionError(
            f"{metric_name}: got={got!r}, expected={expected!r}"
        ) from exc
    if not math.isclose(
        got_number,
        expected_number,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    ):
        raise AssertionError(f"{metric_name}: got={got!r}, expected={expected!r}")
