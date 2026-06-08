"""Boolean wrappers for profile_shape string outputs.

Converts string-based profile_shape classifications into boolean columns
usable in strategy conditions via the is_true/is_false operators.
"""

import pandas as pd

_NORMAL = "NORMAL"
_B_SHAPE = "B_SHAPE"
_P_SHAPE = "P_SHAPE"
_D_SHAPE = "D_SHAPE"
_NEUTRAL = "NEUTRAL"


def _get_shape_column(df: pd.DataFrame) -> pd.Series:
    """Get profile_shape column or compute it lazily."""
    if "profile_shape" not in df.columns:
        from finbar.core.domain.services.profile_shape import classify_all_profile_shapes

        return classify_all_profile_shapes(df)["profile_shape"]
    return df["profile_shape"]


def compute_is_normal_shape(df: pd.DataFrame) -> pd.DataFrame:
    """True where profile_shape == NORMAL.

    NORMAL: bell-shaped volume distribution, balanced session,
    POC near center of value area — typical auction day.

    Args:
        df: Price DataFrame with profile_shape column.

    Returns:
        DataFrame with added is_normal_shape boolean column.
    """
    df = df.copy()
    shape = _get_shape_column(df)
    df["is_normal_shape"] = shape == _NORMAL
    return df


def compute_is_b_shape(df: pd.DataFrame) -> pd.DataFrame:
    """True where profile_shape == B_SHAPE.

    B_SHAPE: bimodal distribution, two volume clusters,
    POC in upper or lower cluster — trend day with pullback.

    Args:
        df: Price DataFrame with profile_shape column.

    Returns:
        DataFrame with added is_b_shape boolean column.
    """
    df = df.copy()
    shape = _get_shape_column(df)
    df["is_b_shape"] = shape == _B_SHAPE
    return df


def compute_is_p_shape(df: pd.DataFrame) -> pd.DataFrame:
    """True where profile_shape == P_SHAPE.

    P_SHAPE: volume concentrated in lower half, POC low,
    thin upper profile — buyers failing to push higher, potential top.

    Args:
        df: Price DataFrame with profile_shape column.

    Returns:
        DataFrame with added is_p_shape boolean column.
    """
    df = df.copy()
    shape = _get_shape_column(df)
    df["is_p_shape"] = shape == _P_SHAPE
    return df


def compute_is_d_shape(df: pd.DataFrame) -> pd.DataFrame:
    """True where profile_shape == D_SHAPE.

    D_SHAPE: volume concentrated in upper half, POC high,
    thin lower profile — sellers failing to push lower, potential bottom.

    Args:
        df: Price DataFrame with profile_shape column.

    Returns:
        DataFrame with added is_d_shape boolean column.
    """
    df = df.copy()
    shape = _get_shape_column(df)
    df["is_d_shape"] = shape == _D_SHAPE
    return df


def compute_is_neutral_shape(df: pd.DataFrame) -> pd.DataFrame:
    """True where profile_shape == NEUTRAL.

    NEUTRAL: flat or noisy distribution, no clear clustering,
    ambiguous session — indecision or low participation.

    Args:
        df: Price DataFrame with profile_shape column.

    Returns:
        DataFrame with added is_neutral_shape boolean column.
    """
    df = df.copy()
    shape = _get_shape_column(df)
    df["is_neutral_shape"] = shape == _NEUTRAL
    return df
