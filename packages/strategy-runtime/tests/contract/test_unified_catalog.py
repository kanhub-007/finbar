"""Contract tests for UnifiedMetricCatalog.

Covers the unified catalog's dual role (parser validation via
IndicatorCapabilityProvider + capability checks via MarketMetricCatalog)
and the handler-required parser gate (resolve() agrees with
supports_concrete() / UsableMetricSet for every registry metric).
"""

import pytest

from finbar_strategy_runtime.domain.entities.metric_confidence import (
    MetricConfidence,
)
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)
from finbar_strategy_runtime.domain.interfaces.market_metric_catalog import (
    MarketMetricCatalog,
)


@pytest.fixture
def catalog():
    """Build a UnifiedMetricCatalog.

    The catalog auto-imports the indicator calculator on construction,
    so all @_register handlers are populated automatically.
    """
    from finbar_strategy_runtime.parser.unified_metric_catalog import (
        UnifiedMetricCatalog,
    )

    return UnifiedMetricCatalog()


# ---------------------------------------------------------------------------
# Scenario 1.1: Unified catalog serves both parser validation and capability
# ---------------------------------------------------------------------------


class TestUnifiedCatalogDualRole:
    """The catalog must implement both interfaces and answer consistently."""

    def test_implements_both_interfaces(self, catalog):
        """UnifiedMetricCatalog is both an IndicatorCapabilityProvider
        and a MarketMetricCatalog."""
        assert isinstance(catalog, IndicatorCapabilityProvider)
        assert isinstance(catalog, MarketMetricCatalog)

    def test_parser_indicator_supported_and_computable(self, catalog):
        """An existing parser indicator (vwap) is supported + computable."""
        assert catalog.supports_concrete("vwap") is True

        result = catalog.check("vwap", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True

    def test_old_period_based_name_still_works(self, catalog):
        """sma_20 (period-based) is still recognised by the parser side."""
        assert catalog.supports_concrete("sma_20") is True

    def test_new_metric_supported_and_computable(self, catalog):
        """A catalogued OHLCV metric with a registered handler is computable."""
        assert catalog.supports_concrete("corwin_schultz_spread") is True

        result = catalog.check("corwin_schultz_spread", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_unknown_name_not_supported(self, catalog):
        """An unknown metric name is not supported."""
        assert catalog.supports_concrete("nonexistent_metric") is False

        result = catalog.check("nonexistent_metric", "daily_ohlcv")
        assert result.supported is False
        assert result.computable is False

    def test_intraday_metric_now_computable(self, catalog):
        """realized_vol_5m is now implemented with a handler."""
        assert catalog.supports_concrete("realized_vol_5m") is True

        result = catalog.check("realized_vol_5m", "intraday_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.ACTUAL

    def test_check_returns_confidence_for_computable(self, catalog):
        """A computable parser indicator returns a confidence level."""
        result = catalog.check("vwap", "daily_ohlcv")
        assert result.confidence is not None

    def test_proxy_indicator_reports_proxy_confidence(self, catalog):
        """A proxy_-prefixed indicator reports PROXY confidence, not ACTUAL."""
        result = catalog.check("proxy_atr", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_get_returns_definition(self, catalog):
        """get() returns the MarketMetricDefinition for a catalogued name."""
        definition = catalog.get("corwin_schultz_spread")
        assert definition is not None
        assert definition.name == "corwin_schultz_spread"
        assert definition.family == MetricFamily.SPREAD

    def test_get_returns_none_for_unknown(self, catalog):
        """get() returns None for an unknown name."""
        assert catalog.get("nonexistent") is None

    def test_list_returns_all_metrics(self, catalog):
        """list() returns a non-empty sequence of definitions."""
        items = catalog.list()
        assert len(items) > 50  # we have ~110 entries

    def test_list_filtered_by_family(self, catalog):
        """list(family=...) filters by MetricFamily."""
        items = catalog.list(family=MetricFamily.SPREAD)
        assert len(items) > 0
        assert all(m.family == MetricFamily.SPREAD for m in items)

    def test_resolve_best_for_volatility_concept(self, catalog):
        """resolve_best('volatility', ...) selects yang_zhang_vol for daily."""
        result = catalog.resolve_best("volatility", "daily_ohlcv", interval="1d")
        assert result.supported is True
        assert result.computable is True
        assert result.selected_metric == "yang_zhang_vol"
        assert result.confidence == MetricConfidence.PROXY

    def test_supported_concrete_names_includes_old_indicators(self, catalog):
        """supported_concrete_names() includes existing parser indicators."""
        names = catalog.supported_concrete_names()
        assert "vwap" in names
        assert "atr" in names


# ---------------------------------------------------------------------------
# Scenario 1.3: Handler registration enforces name-sync invariant
# ---------------------------------------------------------------------------


class TestNameSyncInvariant:
    """Every handler name must be catalogued; catalogued names without
    handlers must report computable=False."""

    def test_every_handler_accepted_by_parser(self, catalog):
        """Every registered handler name must be accepted by supports_concrete().

        This is the name-sync invariant: if a handler exists for a name,
        the parser must accept that name. Otherwise the handler computes
        a column the parser would reject as unknown_operand.
        """
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
        )

        handler_names = set(_INDICATOR_HANDLERS.keys())
        unaccepted = {
            name for name in handler_names if not catalog.supports_concrete(name)
        }
        assert unaccepted == set(), f"Handlers not accepted by parser: {unaccepted}"

    def test_catalogued_without_handler_not_computable(self, catalog):
        """Catalogued names that lack a handler report computable=False."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
        )

        catalog_names = catalog.all_metric_names()
        handler_names = set(_INDICATOR_HANDLERS.keys())

        for name in catalog_names - handler_names:
            result = catalog.check(name, "daily_ohlcv")
            assert (
                result.computable is False or not result.supported
            ), f"'{name}' has no handler but check() returned computable=True"

    def test_unhandled_metrics_rejected_by_parser(self, catalog):
        """Catalogued MarketMetricDefinitions WITHOUT a handler must be
        rejected by supports_concrete() so users can't reference them.

        This only applies to names in _metric_registry (MarketMetricDefinition
        entries). Dynamic/parameterized names like sma_5, atr_2 are accepted
        via pattern matching in the legacy strategy catalog.
        """
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
        )
        from finbar_strategy_runtime.parser._metric_registry import (
            CONCEPTUAL_METRICS,
            METRICS,
        )

        handler_names = set(_INDICATOR_HANDLERS.keys())
        market_metric_names = {m.name for m in METRICS + CONCEPTUAL_METRICS}

        # Every market metric without a handler must be rejected
        leaked = {
            name
            for name in market_metric_names - handler_names
            if catalog.supports_concrete(name)
        }
        assert leaked == set(), (
            f"Market metrics without handlers are parser-accepted "
            f"(users can reference them but they produce no column): {leaked}"
        )


# ---------------------------------------------------------------------------
# Handler-required parser gate (Spec 2026-06-15)
# ---------------------------------------------------------------------------


# Representative sample across every theory family blocked by the original
# resolve() bug (see spec 01-story.md blast-radius table).
_HANDLED_FAMILY_SAMPLE = [
    # VSA
    "bag_holding",
    "effort_result_divergence",
    "stopping_volume",
    "no_demand",
    # SMC / ICT
    "bos",
    "choch",
    "bullish_fvg",
    # Bill Williams
    "alligator_jaw",
    "alligator_status",
    # Fibonacci
    "fib_618_retrace",
    # Microstructure
    "corwin_schultz_spread",
    # Derivatives
    "funding_rate",
    # Regime
    "market_regime",
    "hurst_exponent",
]


class TestResolveHandlerGate:
    """The parser gate is resolve(). It must agree with UsableMetricSet and
    accept every catalogued metric that has a registered handler."""

    # --- Scenario 1: catalogued + handled metric resolves to its name ---

    @pytest.mark.parametrize("metric", _HANDLED_FAMILY_SAMPLE)
    def test_catalogued_handled_metric_resolves(self, catalog, metric):
        """resolve() returns the metric's own column name (was None — the bug)."""
        assert catalog.resolve(metric, None) == metric

    def test_mixed_case_input_is_lowercased_before_lookup(self, catalog):
        """resolve() lowercases, matching _parse_one's convention."""
        assert catalog.resolve("Bag_Holding", None) == "bag_holding"
        assert catalog.resolve("BAG_HOLDING", None) == "bag_holding"

    # --- Scenario 2: catalogued WITHOUT handler still rejected ---

    def test_catalogued_unhandled_metric_rejected(self, catalog):
        """Catalogued-but-unimplemented metrics must NOT resolve (INV-5)."""
        from finbar_strategy_runtime.indicators._handler_registry import (
            _INDICATOR_HANDLERS,
        )
        from finbar_strategy_runtime.parser._metric_registry import (
            CONCEPTUAL_METRICS,
            METRICS,
        )

        handler_names = set(_INDICATOR_HANDLERS.keys())
        registry_names = {m.name for m in METRICS + CONCEPTUAL_METRICS}
        for name in registry_names - handler_names:
            assert (
                catalog.resolve(name, None) is None
            ), f"{name!r} has no handler but resolve() accepted it (over-correction)"

    # --- Scenario 3: unknown metric still rejected ---

    def test_unknown_metric_rejected(self, catalog):
        assert catalog.resolve("totally_made_up_metric", None) is None
        assert catalog.resolve("not_a_real_indicator", None) is None

    # --- Scenario 4: legacy fixed + period-parameterised still resolve ---

    @pytest.mark.parametrize(
        "metric",
        [
            "vp_vah",
            "vp_val",
            "vp_poc",
            "vwap",
            "above_value",
            "acceptance_into_value",
            "value_area_width_pct",
            "poc_slope_5",
            "is_markdown",
            "is_distribution",
        ],
    )
    def test_legacy_fixed_indicators_resolve(self, catalog, metric):
        assert catalog.resolve(metric, None) == metric

    @pytest.mark.parametrize(
        "name,period,expected",
        [
            ("sma", 50, "sma_50"),
            ("rsi", 14, "rsi_14"),
            ("ema", 12, "ema_12"),
            ("atr", 2, "atr_2"),
            # Pattern-matched rolling-VP (delegate to legacy):
            ("vp_poc_10d", None, "vp_poc_10d"),
            ("rvp_vah_48", None, "rvp_vah_48"),
            ("cvp_val_20d", None, "cvp_val_20d"),
        ],
    )
    def test_period_parameterised_names_resolve(self, catalog, name, period, expected):
        assert catalog.resolve(name, period) == expected

    # --- Scenario 6: all parser-side methods derive from UsableMetricSet ---

    def test_resolve_and_supports_concrete_agree_for_every_registry_name(self, catalog):
        """resolve() and supports_concrete() must agree for every registry name
        (INV-3). They both derive from the single UsableMetricSet instance."""
        from finbar_strategy_runtime.parser._metric_registry import (
            CONCEPTUAL_METRICS,
            METRICS,
        )

        for name in (m.name for m in METRICS + CONCEPTUAL_METRICS):
            resolved = catalog.resolve(name, None)
            supported = catalog.supports_concrete(name)
            assert (
                resolved is not None
            ) == supported, (
                f"{name!r}: resolve={resolved!r} but supports_concrete={supported}"
            )

    def test_catalog_delegates_registry_resolution_to_usable_set(self, catalog):
        """For every registry name, resolve()/supports_concrete() must equal
        the _usable collaborator's answer (no re-encoded rule)."""
        from finbar_strategy_runtime.parser._metric_registry import (
            CONCEPTUAL_METRICS,
            METRICS,
        )

        usable = catalog._usable
        for name in (m.name for m in METRICS + CONCEPTUAL_METRICS):
            assert catalog.resolve(name, None) == usable.resolve(name), name
            assert catalog.supports_concrete(name) == usable.contains(name), name

    def test_every_handler_accepted_by_resolve(self, catalog):
        """Every registered handler that is also catalogued must resolve.

        This is the strengthened name-sync invariant: the original bug escaped
        because the test asserted on supports_concrete() (which worked) instead
        of resolve() (the actual parser gate, which was broken)."""
        from finbar_strategy_runtime.indicators._handler_registry import (
            _INDICATOR_HANDLERS,
        )
        from finbar_strategy_runtime.parser._metric_registry import (
            CONCEPTUAL_METRICS,
            METRICS,
        )

        registry_names = {m.name for m in METRICS + CONCEPTUAL_METRICS}
        for name in set(_INDICATOR_HANDLERS) & registry_names:
            assert catalog.resolve(name, None) == name, name

    # --- Scenario 7: construction-time consistency (fail-loud, INV-6) ---

    def test_fresh_catalog_constructs_without_error(self):
        """A correctly-wired catalog does NOT raise on construction."""
        from finbar_strategy_runtime.parser.unified_metric_catalog import (
            UnifiedMetricCatalog,
        )

        catalog = UnifiedMetricCatalog()  # must not raise
        assert catalog.resolve("bag_holding", None) == "bag_holding"

    def test_validate_consistency_raises_on_resolve_drift(self, catalog):
        """If _usable disagrees with ground truth, _validate_consistency raises.

        Sabotage: rebuild _usable with the real ``by_name`` but an empty
        handler set. Every catalogued+handled metric now appears unusable to
        ``_usable`` while ground truth (``_handled_names``) says it is usable.
        The validator must catch this disagreement and name a divergent metric.
        """
        from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet

        catalog._usable = UsableMetricSet(by_name=catalog._by_name, handled_names=set())
        with pytest.raises(RuntimeError) as exc:
            catalog._validate_consistency()
        msg = str(exc.value).lower()
        # The validator must flag the inconsistency and name some divergent
        # metric (which one fires first is insertion-order dependent).
        assert "inconsistent" in msg, exc.value
        known_handled = [n for n in ("bag_holding", "corwin_schultz_spread", "bos")]
        assert any(n in str(exc.value) for n in known_handled), exc.value

    def test_validate_consistency_raises_when_supports_concrete_drifts(
        self, catalog, monkeypatch
    ):
        """The validator also catches supports_concrete() disagreeing with
        _usable (the reverse disagreement)."""
        # Make supports_concrete lie for one usable name while resolve stays true.
        usable_names = catalog._usable.names()
        victim = next(iter(usable_names))

        original_supports = catalog.supports_concrete

        def lying_supports(name: str) -> bool:
            if name == victim:
                return False
            return original_supports(name)

        monkeypatch.setattr(catalog, "supports_concrete", lying_supports)
        with pytest.raises(RuntimeError) as exc:
            catalog._validate_consistency()
        assert "supports_concrete" in str(exc.value).lower(), exc.value

    # --- Scenario 8: adding a metric needs zero catalog-code edits ---

    def test_new_metric_auto_wires_without_catalog_edits(self, catalog):
        """A metric known to both by_name and handled_names is usable across
        all four parser-side methods with no per-method wiring.

        Simulates a developer adding a ``MarketMetricDefinition`` to
        ``_metric_registry`` (→ ``_by_name``) and registering a handler
        (→ ``_handled_names``). No catalog method is edited per-metric.
        """
        from finbar_strategy_runtime.domain.entities.market_metric_definition import (
            MarketMetricDefinition,
        )
        from finbar_strategy_runtime.domain.entities.metric_family import (
            MetricFamily,
        )
        from finbar_strategy_runtime.parser.usable_metric_set import UsableMetricSet

        new_def = MarketMetricDefinition(
            name="brand_new_metric", family=MetricFamily.PRICE_ACTION
        )
        # Mirror exactly what construction would do: add to _by_name and the
        # handler set, then rebuild the single usable-set collaborator.
        catalog._by_name["brand_new_metric"] = new_def
        catalog._handled_names.add("brand_new_metric")
        catalog._usable = UsableMetricSet(
            by_name=catalog._by_name,
            handled_names=catalog._handled_names,
        )

        assert catalog.resolve("brand_new_metric", None) == "brand_new_metric"
        assert catalog.supports_concrete("brand_new_metric") is True
        assert "brand_new_metric" in catalog.supported_concrete_names()
        assert "brand_new_metric" in catalog.as_dict()["fixed_indicators"]


# ---------------------------------------------------------------------------
# Discovery: handled metrics surface in capabilities (Spec Slice 2)
# ---------------------------------------------------------------------------


# Representative handled metrics that must appear in the discovery payload.
_DISCOVERY_SAMPLE = [
    "bag_holding",
    "market_regime",
    "hurst_exponent",
    "bos",
    "choch",
    "alligator_jaw",
    "fib_618_retrace",
    "corwin_schultz_spread",
]


class TestDiscoverySurfacesHandledMetrics:
    """as_dict()['fixed_indicators'] must include every catalogued metric that
    has a registered handler, plus the legacy fixed indicators."""

    @pytest.mark.parametrize("metric", _DISCOVERY_SAMPLE)
    def test_handled_metric_in_capabilities(self, catalog, metric):
        assert metric in catalog.as_dict()["fixed_indicators"]

    @pytest.mark.parametrize(
        "legacy", ["vp_vah", "atr", "vwap", "acceptance_into_value"]
    )
    def test_legacy_metrics_still_in_capabilities(self, catalog, legacy):
        assert legacy in catalog.as_dict()["fixed_indicators"]

    def test_fixed_indicators_is_superset_of_usable_set(self, catalog):
        """Every usable registry metric is surfaced in fixed_indicators."""
        fixed = set(catalog.as_dict()["fixed_indicators"])
        assert catalog._usable.names() <= fixed

    def test_fixed_indicators_is_sorted_and_unique(self, catalog):
        fixed = catalog.as_dict()["fixed_indicators"]
        assert fixed == sorted(set(fixed))
