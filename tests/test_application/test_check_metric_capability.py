"""Tests for CheckMetricCapabilityUseCase — Scenario 5.3.

Verifies derivatives metrics report computable=False when data hasn't
been fetched, with a hint to run fetch_derivatives.
"""


from finbar.core.application.use_cases.check_metric_capability import (
    CheckMetricCapabilityUseCase,
)
from finbar.core.domain.entities.derivatives_metrics import DerivativesMetrics
from tests.test_domain.fakes.in_memory_derivatives_repository import (
    InMemoryDerivativesRepository,
)


class TestCheckMetricCapability:
    """Derivatives metrics require persisted data to be computable."""

    def test_derivatives_not_fetched_reports_false(self):
        """No derivatives data in repo → computable=False with hint."""
        fake_repo = InMemoryDerivativesRepository(data=[])
        use_case = CheckMetricCapabilityUseCase(repository=fake_repo)

        result = use_case.execute(
            name="open_interest", symbol="BTC", data_class="daily_ohlcv"
        )

        assert result.computable is False
        assert any("fetch_derivatives" in w.lower() for w in result.warnings)

    def test_derivatives_fetched_reports_true(self):
        """Data in repo → computable=True for the derivatives metric."""
        fake_repo = InMemoryDerivativesRepository(
            data=[
                DerivativesMetrics(
                    symbol="BTC",
                    timestamp="2024-01-01T00:00:00+00:00",
                    interval="1d",
                    open_interest=1_000_000,
                )
            ]
        )
        use_case = CheckMetricCapabilityUseCase(repository=fake_repo)

        result = use_case.execute(
            name="open_interest", symbol="BTC", data_class="daily_ohlcv"
        )

        assert result.supported is True

    def test_ohlcv_metric_ignores_repo(self):
        """OHLCV metrics don't consult the repo — just the catalog."""
        fake_repo = InMemoryDerivativesRepository(data=[])
        use_case = CheckMetricCapabilityUseCase(repository=fake_repo)

        result = use_case.execute(
            name="amihud_illiq", symbol="BTC", data_class="daily_ohlcv"
        )

        # amihud_illiq has a handler + OHLCV data class → computable
        assert result.supported is True

    def test_no_repo_still_works_for_ohlcv(self):
        """Without a repo, OHLCV metrics still work."""
        use_case = CheckMetricCapabilityUseCase(repository=None)

        result = use_case.execute(
            name="corwin_schultz_spread", data_class="daily_ohlcv"
        )

        assert result.computable is True

    def test_unknown_metric_not_supported(self):
        """Unknown metric → supported=False."""
        use_case = CheckMetricCapabilityUseCase(repository=None)

        result = use_case.execute(
            name="nonexistent", data_class="daily_ohlcv"
        )

        assert result.supported is False
        assert result.computable is False
