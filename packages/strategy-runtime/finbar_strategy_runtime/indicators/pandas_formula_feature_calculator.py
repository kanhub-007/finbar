"""PandasFormulaFeatureCalculator — pandas implementation of formula features."""

import logging
from typing import Any

import pandas as pd

from finbar_strategy_runtime.domain.entities.formula_node import FormulaNode
from finbar_strategy_runtime.domain.interfaces.formula_feature_calculator import (
    FormulaFeatureCalculator,
)

logger = logging.getLogger(__name__)

_COMPARISON_OPS = frozenset({">", "<", ">=", "<=", "==", "!="})
_ARITHMETIC_OPS = frozenset({"+", "-", "*", "/"})
_LOGICAL_OPS = frozenset({"and", "or"})
_UNARY_OPS = frozenset({"not", "abs", "neg"})


class PandasFormulaFeatureCalculator(FormulaFeatureCalculator):
    """Evaluate formula expression trees using pandas Series operations."""

    def calculate(self, frame: pd.DataFrame, features: list[dict]) -> pd.DataFrame:
        """Add formula feature columns and return the enriched DataFrame."""
        result = frame.copy()
        for feature in features:
            if feature.get("type") != "formula":
                continue
            name = feature["name"]
            expr = feature.get("expr")
            if not isinstance(expr, dict):
                continue
            node = _parse_node(expr)
            try:
                result[name] = _evaluate(node, result)
            except Exception:
                result[name] = pd.Series(float("nan"), index=result.index)
        return result


def _parse_node(raw: dict) -> FormulaNode:
    """Parse a dict expression into a FormulaNode tree."""
    if not isinstance(raw, dict):
        return _parse_operand(raw)
    op = raw.get("op", "")
    if op in _COMPARISON_OPS | _ARITHMETIC_OPS:
        children = raw.get("children", [])
        if children and len(children) >= 2:
            return FormulaNode(
                op=op,
                left=_parse_operand(children[0]),
                right=_parse_operand(children[1]),
            )
        return FormulaNode(
            op=op,
            left=_parse_operand(raw.get("left")),
            right=_parse_operand(raw.get("right")),
        )
    if op in _LOGICAL_OPS:
        children = raw.get("children", raw.get("operands", []))
        if not children and "left" in raw and "right" in raw:
            children = [raw["left"], raw["right"]]
        return FormulaNode(
            op=op,
            children=[
                _parse_node(c) if isinstance(c, dict) else _parse_operand(c)
                for c in children
            ],
        )
    if op in _UNARY_OPS:
        return FormulaNode(
            op=op,
            left=_parse_operand(raw.get("operand", raw.get("left"))),
        )
    return _parse_operand(raw)


def _parse_operand(raw: Any) -> FormulaNode:
    """Parse a leaf operand."""
    if isinstance(raw, bool):
        return FormulaNode(kind="literal", value=raw, label=str(raw))
    if isinstance(raw, (int, float)):
        return FormulaNode(kind="literal", value=float(raw), label=str(raw))
    if isinstance(raw, str):
        return FormulaNode(kind="indicator", value=raw, label=raw)
    if isinstance(raw, dict):
        # A nested expression tree (dict carrying a recognized ``op``) must
        # recurse through _parse_node. Without this, an inner arithmetic
        # node like {op: '-', left: close, right: sma_20} was treated as a
        # leaf and resolved to literal 0, silently NaN-ing the whole feature.
        op = raw.get("op", "")
        if op in _COMPARISON_OPS | _ARITHMETIC_OPS | _LOGICAL_OPS | _UNARY_OPS:
            return _parse_node(raw)
        kind = raw.get("kind", "indicator")
        value = raw.get("value", raw.get("indicator", raw.get("field", 0)))
        label = raw.get("label", str(value))
        return FormulaNode(kind=kind, value=value, label=label)
    return FormulaNode(kind="literal", value=0.0, label="0")


def _value(node: FormulaNode, df: pd.DataFrame) -> pd.Series:
    """Resolve a node that may be either a leaf or a nested expression.

    Op-bearing nodes (produced when ``_parse_operand`` recurses into a nested
    expression tree) are evaluated; leaf nodes are resolved directly. This is
    the single dispatch point that lets arithmetic/comparison operands be
    themselves arbitrary expressions instead of leaves only.
    """
    if node.op:
        return _evaluate(node, df)
    return _resolve(node, df)


def _evaluate(node: FormulaNode, df: pd.DataFrame) -> pd.Series:
    """Evaluate a formula tree against a DataFrame and return a Series."""
    if node.op in _COMPARISON_OPS:
        return _compare(node.op, _value(node.left, df), _value(node.right, df))
    if node.op in _ARITHMETIC_OPS:
        return _arithmetic(node.op, _value(node.left, df), _value(node.right, df))
    if node.op in _LOGICAL_OPS:
        results = [_evaluate(c, df) for c in node.children]
        return _logical(node.op, results)
    if node.op == "not":
        return ~_value(node.left, df).astype(bool)
    if node.op == "abs":
        return _value(node.left, df).abs()
    if node.op == "neg":
        return -_value(node.left, df)
    return _resolve(node, df)


def _resolve(node: FormulaNode, df: pd.DataFrame) -> pd.Series:
    """Resolve a leaf operand to a pandas Series."""
    if node.kind == "literal":
        return pd.Series(node.value, index=df.index)
    column = str(node.value)
    if column in df.columns:
        return pd.to_numeric(df[column], errors="coerce")
    return pd.Series(float("nan"), index=df.index)


def _compare(op: str, left: pd.Series, right: pd.Series) -> pd.Series:
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return pd.Series(False, index=left.index)


def _arithmetic(op: str, left: pd.Series, right: pd.Series) -> pd.Series:
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        return left / right.replace(0, float("nan"))
    return pd.Series(float("nan"), index=left.index)


def _logical(op: str, results: list[pd.Series]) -> pd.Series:
    if not results:
        return pd.Series(False, index=results[0].index if results else None)
    result = results[0].astype(bool)
    for r in results[1:]:
        if op == "and":
            result = result & r.astype(bool)
        else:
            result = result | r.astype(bool)
    return result
