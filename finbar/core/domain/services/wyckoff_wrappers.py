"""Boolean wrappers for Wyckoff phase string outputs.

Converts string-based wyckoff_phase classifications into boolean columns
usable in strategy conditions via the is_true/is_false operators.
"""

import pandas as pd

_ACCUMULATION = "ACCUMULATION"
_MARKUP = "MARKUP"
_DISTRIBUTION = "DISTRIBUTION"
_MARKDOWN = "MARKDOWN"
_NEUTRAL = "NEUTRAL"


def _get_phase_column(df: pd.DataFrame) -> pd.Series:
    """Get wyckoff_phase column or compute it lazily."""
    if "wyckoff_phase" not in df.columns:
        from finbar.core.domain.services.wyckoff_phase import classify_wyckoff_phase

        return classify_wyckoff_phase(df)["wyckoff_phase"]
    return df["wyckoff_phase"]


def compute_is_accumulation(df: pd.DataFrame) -> pd.DataFrame:
    """True where wyckoff_phase == ACCUMULATION.

    ACCUMULATION: quiet ranging with POC stabilizing, low volume,
    narrow value area — buyers quietly absorbing supply.

    Args:
        df: Price DataFrame with wyckoff_phase column.

    Returns:
        DataFrame with added is_accumulation boolean column.
    """
    df = df.copy()
    phase = _get_phase_column(df)
    df["is_accumulation"] = phase == _ACCUMULATION
    return df


def compute_is_markup(df: pd.DataFrame) -> pd.DataFrame:
    """True where wyckoff_phase == MARKUP.

    MARKUP: POC rising steadily, value area expanding or holding,
    price pushing higher — institutional mark-up phase.

    Args:
        df: Price DataFrame with wyckoff_phase column.

    Returns:
        DataFrame with added is_markup boolean column.
    """
    df = df.copy()
    phase = _get_phase_column(df)
    df["is_markup"] = phase == _MARKUP
    return df


def compute_is_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """True where wyckoff_phase == DISTRIBUTION.

    DISTRIBUTION: POC peaking/declining, elevated volume,
    price stalling at highs — smart money distributing to late buyers.

    Args:
        df: Price DataFrame with wyckoff_phase column.

    Returns:
        DataFrame with added is_distribution boolean column.
    """
    df = df.copy()
    phase = _get_phase_column(df)
    df["is_distribution"] = phase == _DISTRIBUTION
    return df


def compute_is_markdown(df: pd.DataFrame) -> pd.DataFrame:
    """True where wyckoff_phase == MARKDOWN.

    MARKDOWN: POC falling steadily, widening value area,
    breakdown in progress — institutional selling drive.

    Args:
        df: Price DataFrame with wyckoff_phase column.

    Returns:
        DataFrame with added is_markdown boolean column.
    """
    df = df.copy()
    phase = _get_phase_column(df)
    df["is_markdown"] = phase == _MARKDOWN
    return df


def compute_is_wyckoff_neutral(df: pd.DataFrame) -> pd.DataFrame:
    """True where wyckoff_phase == NEUTRAL.

    NEUTRAL: no clear Wyckoff phase detected — mixed or
    transitioning market structure.

    Args:
        df: Price DataFrame with wyckoff_phase column.

    Returns:
        DataFrame with added is_wyckoff_neutral boolean column.
    """
    df = df.copy()
    phase = _get_phase_column(df)
    df["is_wyckoff_neutral"] = phase == _NEUTRAL
    return df
