"""UsableMetricSet — single source of truth for parser-usable registry metrics.

A metric is usable in a strategy iff it is BOTH catalogued
(``MarketMetricDefinition`` in ``_metric_registry``) AND has a registered
computation handler (``_INDICATOR_HANDLERS``). This value object owns
that rule once, so ``UnifiedMetricCatalog`` cannot re-encode it across
methods (the drift cause of the original ``resolve()`` bug).

Purity: immutable after construction. No framework, I/O, or global
state. Unit-testable with zero infrastructure.
"""

from collections.abc import Collection, Mapping


class UsableMetricSet:
    """Immutable view of the registry metrics usable in strategies.

    The usable set is the intersection of catalogued names (``by_name``)
    and handled names (``handled_names``). It is computed once at
    construction and cached. Name lookups are case-insensitive
    (lowercased), matching the strategy parser's ``_parse_one``
    convention.
    """

    def __init__(
        self,
        by_name: Mapping[str, object],
        handled_names: Collection[str],
    ) -> None:
        """Store the inputs defensively and compute the usable intersection.

        Args:
            by_name: Catalogued metric names → definitions (e.g. the
                catalog's ``_by_name``). Only the keys are consulted.
            handled_names: Names with a registered computation handler
                (e.g. ``_INDICATOR_HANDLERS.keys()``).
        """
        # Defensive-copy so later mutation of caller collections cannot
        # change the usable set (immutability).
        self._by_name: Mapping[str, object] = dict(by_name)
        self._handled: frozenset[str] = frozenset(n.lower() for n in handled_names)
        # Compute the usable intersection once (INV-1); cache it (INV-2).
        # Keys are normalised to lowercase so resolve()/contains() — which
        # lowercase their input — can always find a mixed-case registry
        # name (e.g. ``MarketMetricDefinition(name="RSI_Divergence")``).
        self._usable: frozenset[str] = frozenset(
            n.lower() for n in self._by_name if n.lower() in self._handled
        )

    def resolve(self, name: str) -> str | None:
        """Return the lowercased ``name`` if usable, else ``None``.

        A name is usable iff it is in both ``by_name`` and
        ``handled_names`` (INV-1, INV-5).
        """
        n = name.lower()
        return n if n in self._usable else None

    def contains(self, name: str) -> bool:
        """Return True iff ``name`` is usable (INV-1)."""
        return name.lower() in self._usable

    def names(self) -> frozenset[str]:
        """Return the cached usable intersection (INV-2 single source)."""
        return self._usable

    def __len__(self) -> int:
        """Return the number of usable metrics."""
        return len(self._usable)
