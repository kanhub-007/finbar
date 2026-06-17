"""Docs-drift test for proxy section — spec 2026-06-16_unify-proxy-indicator-dispatch Scenario 8.

Guards the human-readable metric catalog against divergence from the
runtime registry. After the dispatch unification, METRIC_CATALOG.md §19
must document all 12 proxy metrics.

Classical school: parse the real markdown file, assert candidate row
counts and per-proxy row presence. No mocks.
"""

from pathlib import Path

import pytest

CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "METRIC_CATALOG.md"
)

ALL_PROXIES = [
    "proxy_atr",
    "proxy_vwap",
    "proxy_ibs",
    "proxy_ib_high",
    "proxy_ib_low",
    "proxy_expected_move",
    "proxy_iv",
    "proxy_parkinson",
    "proxy_garman_klass",
    "proxy_rogers_satchell",
    "proxy_typical_price",
    "proxy_ohlc4",
]


class TestProxyCatalogDocs:
    """Scenario 8 — all 12 proxies documented in METRIC_CATALOG.md §19."""

    def _proxy_section_rows(self) -> list[str]:
        """Return every table row in section 19 (Quantitative Proxies)."""
        text = CATALOG_PATH.read_text(encoding="utf-8")
        in_section = False
        rows: list[str] = []
        for line in text.splitlines():
            trimmed = line.strip()
            if "Quantitative Proxies" in trimmed and trimmed.startswith("##"):
                in_section = True
                continue
            if in_section:
                if trimmed.startswith("##") and "Quantitative" not in trimmed:
                    break
                if trimmed.startswith("|") and not trimmed.startswith("|--"):
                    rows.append(trimmed)
        return rows

    def test_section_contains_all_twelve_proxies(self):
        """Every proxy name in ALL_PROXIES appears as a first-column cell."""
        rows = self._proxy_section_rows()
        for name in ALL_PROXIES:
            found = any(f"| `{name}` |" in r for r in rows)
            assert found, (
                f"`{name}` not found in METRIC_CATALOG.md §19. "
                f"Rows: {rows}"
            )

    def test_section_does_not_contain_duplicates(self):
        """No proxy name appears twice (each gets one row, in its own cell)."""
        rows = self._proxy_section_rows()
        for name in ALL_PROXIES:
            # Must match at cell boundary: "| `proxy_vwap` |"
            count = sum(1 for r in rows if f"| `{name}` |" in r)
            assert count == 1, f"`{name}` appears {count} times"
