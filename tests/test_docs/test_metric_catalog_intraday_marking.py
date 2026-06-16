"""Docs drift tests for METRIC_CATALOG.md — spec 2026-06-16 Scenario 1.

Guards against the human-readable catalog diverging from runtime
behaviour. ``ib_high``/``ib_low``/``ib_midpoint``/``ib_range`` are
intraday-only (they need session-scoped first-hour bars); the markdown
table must mark them ❌ for Daily and ✅ for Intraday, matching the
runtime ``UnifiedMetricCatalog`` fix (Scenario 3).

Classical school: read the real file, assert on parsed table rows.
"""

from pathlib import Path

import pytest

CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "METRIC_CATALOG.md"
)


def _row(metric: str) -> list[str]:
    """Return the pipe-split cells of the markdown row for ``metric``."""
    text = CATALOG_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"| `{metric}`"):
            return [cell.strip() for cell in stripped.split("|")]
    raise AssertionError(f"{metric} row not found in METRIC_CATALOG.md")


class TestIntradayOnlyDocs:
    """Scenario 1 — ib_* marked intraday-only in the catalog docs."""

    @pytest.mark.parametrize(
        "metric",
        ["ib_high", "ib_low", "ib_midpoint", "ib_range"],
    )
    def test_ib_metric_marked_intraday_only(self, metric):
        """ib_* row: Daily = ❌, Intraday = ✅.

        Table columns: | Indicator | Type | Daily | Intraday | Description |
        → Daily is cell index 3, Intraday is cell index 4.
        """
        cells = _row(metric)
        assert "❌" in cells[3], f"{metric} Daily should be ❌: {cells}"
        assert "✅" in cells[4], f"{metric} Intraday should be ✅: {cells}"

    def test_catalog_explains_intraday_only_constraint(self):
        """A footnote/description explains why ib_* need session-scoped data."""
        text = CATALOG_PATH.read_text(encoding="utf-8").lower()
        assert "intraday" in text and "session" in text


class TestMinimumBarRequirementDocs:
    """Scenario 13 — min bar requirements documented in METRIC_CATALOG.md."""

    @pytest.mark.parametrize(
        "metric, min_bars",
        [
            ("hurst_exponent", 100),
            ("market_regime", 220),
            ("effective_tick_spread", 60),
            ("lot_zero_return_spread", 60),
        ],
    )
    def test_min_bar_requirement_in_description(self, metric, min_bars):
        """The row must state the minimum bar requirement."""
        row_text = " ".join(_row(metric))
        assert str(min_bars) in row_text, (
            f"{metric} row should mention >= {min_bars} bars: {row_text!r}"
        )
        assert "bar" in row_text.lower() or "lookback" in row_text.lower()
