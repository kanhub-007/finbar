"""Shared fixtures for contract tests that need finbar repo data.

Golden-frame and validator parity tests load SOL bars from the finbar
monorepo database. These fixtures are only available when running inside
the monorepo; they are skipped when the package is installed standalone.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

# Path from packages/strategy-runtime/tests/contract/ to finbar repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _REPO_ROOT / "data" / "finbar.db"
_STRATEGY_YAML = (
    _REPO_ROOT
    / "strategies"
    / "intraday_scalper"
    / "14_amt_value_reject_30m_1h_mtf.yaml"
)
# Committed int-second parity fixtures (Finbot/Hyperliquid production format)
_PARITY_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "parity"
_PARITY_FIXTURES = {
    "30min": _PARITY_DIR / "sol_30min.csv",
    "1h": _PARITY_DIR / "sol_1h.csv",
}

# Marker: tests that need the finbar monorepo DB and strategy YAML
needs_finbar_data = pytest.mark.skipif(
    not _DB_PATH.exists() or not _STRATEGY_YAML.exists(),
    reason="Finbar monorepo data not found (package installed standalone)",
)

# Marker: tests that need the committed parity CSV fixtures
needs_parity_fixtures = pytest.mark.skipif(
    not all(p.exists() for p in _PARITY_FIXTURES.values()),
    reason="Parity CSV fixtures not found",
)


def load_raw_bars(interval: str, limit: int | None = None) -> list[dict]:
    """Load raw OHLCV bars (only base columns, no indicators) from the DB."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    query = (
        "SELECT timestamp, open, high, low, close, volume "
        "FROM price_bar WHERE symbol = 'SOL' AND interval = ? "
        "ORDER BY timestamp ASC"
    )
    if limit is not None:
        query += f" LIMIT {limit}"
    rows = conn.execute(query, (interval,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_parity_bars(interval: str) -> list[dict]:
    """Load OHLCV bars from a committed int-second parity CSV fixture.

    Bars carry an integer ``timestamp`` (Unix seconds), matching
    Finbot/Hyperliquid production bars. OHLCV fields are cast to float.
    """
    path = _PARITY_FIXTURES[interval]
    bars: list[dict] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            bars.append(
                {
                    "timestamp": int(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
    return bars


def parse_production_strategy() -> tuple:
    """Parse the production MTF strategy, return (definition, primary_req, info_req, required_cols)."""
    from finbar_strategy_runtime.parser.strategy_definition_parser import (
        StrategyDefinitionParser,
    )

    yaml_text = _STRATEGY_YAML.read_text(encoding="utf-8")
    validation = StrategyDefinitionParser().parse(yaml_text, {})
    assert validation.valid, f"Strategy parse failed: {validation.errors}"
    definition = validation.definition
    assert definition is not None
    return (
        definition,
        list(validation.primary_required_indicators),
        dict(validation.informative_required_indicators),
        list(validation.required_columns),
    )


@pytest.fixture(scope="module")
def strategy_context() -> tuple:
    """Parse the production strategy (module-scoped for speed)."""
    return parse_production_strategy()


@pytest.fixture(scope="module")
def sol_primary_bars() -> list[dict]:
    """Load SOL 30min raw bars from the DB."""
    return load_raw_bars("30min")


@pytest.fixture(scope="module")
def sol_info_bars() -> dict[str, list[dict]]:
    """Load SOL 1h raw bars from the DB."""
    return {"h1": load_raw_bars("1h")}


@pytest.fixture(scope="module")
def enriched_mtf_frame() -> "pd.DataFrame":
    """Enriched MTF frame (module-scoped for speed)."""
    from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
        MultiTimeframeBarEnricher,
    )
    from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
        PandasBarFrameConverter,
    )
    from finbar_strategy_runtime.indicators.pandas_strategy_feature_calculator import (
        PandasStrategyFeatureCalculator,
    )
    from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
        PandasTaIndicatorCalculator,
    )
    from finbar_strategy_runtime.indicators.pandas_timeframe_bar_merger import (
        PandasTimeframeBarMerger,
    )

    definition, primary_req, info_req, _ = parse_production_strategy()
    primary = load_raw_bars("30min")
    info = {"h1": load_raw_bars("1h")}
    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )
    return enricher.enrich(primary, info, definition, primary_req, info_req)
