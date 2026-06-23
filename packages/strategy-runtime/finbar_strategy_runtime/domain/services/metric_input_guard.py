"""Metric dependency guard — enforces required columns per policy.

Pure helper used by AMT/Wyckoff/VP service functions so they fail clearly
when a required dependency column is missing, instead of silently
substituting neutral/false/zero/NaN values. Behaviour is controlled by
:class:`MetricInputPolicy`.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from finbar_strategy_runtime.domain.entities.metric_dependency_error import (
    MetricDependencyError,
)
from finbar_strategy_runtime.domain.entities.metric_input_policy import (
    DEFAULT_METRIC_INPUT_POLICY,
    MetricInputPolicy,
)


def require_metric_columns(
    df: pd.DataFrame,
    metric_name: str,
    required: Iterable[str],
    policy: MetricInputPolicy = DEFAULT_METRIC_INPUT_POLICY,
) -> None:
    """Enforce that *required* columns are present on *df*.

    Args:
        df: The enriched DataFrame a metric wants to read from.
        metric_name: The metric whose requirements are being checked.
        required: Column names the metric needs.
        policy: How missing columns are handled.

    Raises:
        MetricDependencyError: In STRICT mode when any required column is
            absent.

    Returns:
        None. (In ``WARN_AND_NAN`` / ``RESEARCH_COMPAT`` the caller proceeds
        and is responsible for emitting NaN/UNKNOWN.)
    """
    missing = [col for col in required if col not in df.columns]
    if not missing:
        return
    if policy == MetricInputPolicy.STRICT:
        raise MetricDependencyError(
            metric_name=metric_name,
            missing=missing,
            reason=(
                "Provide the dependency column(s) (e.g. compute the upstream "
                "indicator first) or request the metric through a calculator "
                "that expands transitive dependencies."
            ),
        )
    # Non-strict policies proceed silently; callers emit NaN/UNKNOWN downstream.
    return


__all__ = ["require_metric_columns"]
