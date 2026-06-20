"""Architecture test — verify the strategy runtime package imports nothing
from finbar-the-app, finbot, Hyperliquid SDKs, SQLAlchemy, yfinance, or any
I/O framework.

Scenario S3: No module in ``finbar_strategy_runtime`` imports from ``finbar.``
(the app), ``finbot``, Hyperliquid SDKs, SQLAlchemy, yfinance, or any I/O
framework.
"""

from __future__ import annotations

import ast
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
# packages/strategy-runtime/tests/contract/test_package_purity.py
# .parents[2] = packages/strategy-runtime/
_PACKAGE_ROOT = _THIS_FILE.parents[2]
_SRC_DIR = _PACKAGE_ROOT / "finbar_strategy_runtime"

# Banned import prefixes — any of these in a package module is a violation
_BANNED_PREFIXES = (
    "finbar.",
    "finbot",
    "hyperliquid",
    "sqlalchemy",
    "yfinance",
    "requests",
    "httpx",
    "aiohttp",
    "fastapi",
    "flask",
    "streamlit",
)


def _scan_imports(root: Path) -> list[str]:
    """Walk all .py files under *root* and collect banned import violations."""
    violations: list[str] = []
    for py_file in root.rglob("*.py"):
        # Skip __pycache__ and .venv
        if "__pycache__" in str(py_file) or ".venv" in str(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _check_name(str(py_file), alias.name, violations)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                _check_name(str(py_file), module, violations)
    return violations


def _check_name(
    filepath: str, name: str, violations: list[str]
) -> None:
    """Check if *name* starts with any banned prefix."""
    for prefix in _BANNED_PREFIXES:
        if name.startswith(prefix):
            violations.append(f"{filepath}: imports '{name}'")


class TestPackagePurity:
    """Architecture tests: package imports nothing from app layers."""

    def test_s3_no_app_imports(self):
        """No module imports from finbar/finbot/Hyperliquid/SQLAlchemy/etc."""
        violations = _scan_imports(_SRC_DIR)
        assert not violations, (
            "Package modules must not import from finbar/finbot/"
            "Hyperliquid/SQLAlchemy/yfinance:\n" + "\n".join(violations)
        )

    def test_s8_simulation_subpackage_pure(self):
        """Simulation subpackage imports nothing from finbar/finbot/etc."""
        sim_dir = _SRC_DIR / "simulation"
        violations = _scan_imports(sim_dir)
        assert not violations, (
            "Simulation subpackage must not import from finbar/finbot/"
            "Hyperliquid/SQLAlchemy/yfinance:\n" + "\n".join(violations)
        )
