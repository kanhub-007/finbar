"""Contract tests for UsableMetricSet — Scenario 5 (Slice 1).

Verifies the value object that owns the usable-set rule:
a metric is usable in a strategy iff it is BOTH catalogued
(``MarketMetricDefinition`` in ``_metric_registry``) AND has a registered
computation handler (``_INDICATOR_HANDLERS``).

Classical school: real objects, outcome-based assertions, no mocks.
"""

from finbar_strategy_runtime.domain.entities.market_metric_definition import (
    MarketMetricDefinition,
)
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet


def _def(name: str) -> MarketMetricDefinition:
    """Build a minimal valid MarketMetricDefinition for tests.

    The value object never inspects the definition's fields, so any valid
    instance suffices to populate ``by_name``.
    """
    return MarketMetricDefinition(name=name, family=MetricFamily.PRICE_ACTION)


class TestUsableMetricSetResolve:
    """resolve(name) returns name iff name is in BOTH inputs (INV-1, INV-5)."""

    def test_resolve_requires_both_catalog_and_handler(self):
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names={"a"})
        assert s.resolve("a") == "a"

    def test_resolve_rejects_catalogued_without_handler(self):
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names=set())
        assert s.resolve("a") is None

    def test_resolve_rejects_handler_without_catalog(self):
        s = UsableMetricSet(by_name={}, handled_names={"a"})
        assert s.resolve("a") is None

    def test_resolve_rejects_name_in_neither(self):
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names={"a"})
        assert s.resolve("z") is None


class TestUsableMetricSetContains:
    """contains(name) agrees with resolve(name) is not None (INV-3)."""

    def test_contains_true_when_usable(self):
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names={"a"})
        assert s.contains("a") is True

    def test_contains_false_when_catalogued_without_handler(self):
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names=set())
        assert s.contains("a") is False

    def test_contains_false_when_handler_without_catalog(self):
        s = UsableMetricSet(by_name={}, handled_names={"a"})
        assert s.contains("a") is False

    def test_resolve_and_contains_agree_for_every_input(self):
        s = UsableMetricSet(
            by_name={"a": _def("a"), "b": _def("b"), "c": _def("c")},
            handled_names={"a", "d"},
        )
        for name in ("a", "b", "c", "d", "zzz"):
            assert s.contains(name) == (s.resolve(name) is not None), name


class TestUsableMetricSetNames:
    """names() returns exactly the intersection, cached (INV-2)."""

    def test_names_is_the_intersection(self):
        s = UsableMetricSet(
            by_name={"a": _def("a"), "b": _def("b"), "c": _def("c")},
            handled_names={"a", "b", "d"},
        )
        assert s.names() == frozenset({"a", "b"})

    def test_names_is_cached_identity(self):
        """Two calls to names() return the SAME object (not recomputed)."""
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names={"a"})
        assert s.names() is s.names()

    def test_names_is_a_frozenset(self):
        s = UsableMetricSet(by_name={"a": _def("a")}, handled_names={"a"})
        assert isinstance(s.names(), frozenset)


class TestUsableMetricSetCaseInsensitive:
    """Lowercasing matches the parser convention (_parse_one lowercases)."""

    def test_uppercase_input_resolves_when_lowercase_usable(self):
        s = UsableMetricSet(
            by_name={"bag_holding": _def("bag_holding")}, handled_names={"bag_holding"}
        )
        assert s.resolve("BAG_HOLDING") == "bag_holding"
        assert s.resolve("Bag_Holding") == "bag_holding"

    def test_uppercase_input_contains_agrees(self):
        s = UsableMetricSet(
            by_name={"bag_holding": _def("bag_holding")}, handled_names={"bag_holding"}
        )
        assert s.contains("BAG_HOLDING") is True

    def test_resolve_returns_lowercased_name(self):
        """resolve always returns the canonical lowercased name."""
        s = UsableMetricSet(by_name={"bos": _def("bos")}, handled_names={"bos"})
        assert s.resolve("BOS") == "bos"


class TestUsableMetricSetImmutabilityAndEdgeCases:
    """The value object is immutable; empty inputs are valid."""

    def test_empty_inputs_yield_empty_set(self):
        s = UsableMetricSet(by_name={}, handled_names=set())
        assert s.names() == frozenset()
        assert s.resolve("anything") is None
        assert s.contains("anything") is False
        assert len(s) == 0

    def test_input_mutation_does_not_affect_the_set(self):
        """Defensive copy: mutating caller collections post-construction
        must not change the usable set (immutability)."""
        by_name = {"a": _def("a")}
        handled = {"a"}
        s = UsableMetricSet(by_name=by_name, handled_names=handled)
        # Mutate the caller's collections
        by_name["b"] = _def("b")
        handled.add("b")
        # The value object is unaffected
        assert s.names() == frozenset({"a"})
        assert s.resolve("b") is None

    def test_len_reports_usable_count(self):
        s = UsableMetricSet(
            by_name={"a": _def("a"), "b": _def("b"), "c": _def("c")},
            handled_names={"a", "b"},
        )
        assert len(s) == 2
