"""Tests for domain entities — pure dataclasses."""

from finbar.core.domain.entities.data_mode import DataMode
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import StrategyMeta


class TestSignalResult:
    def test_defaults(self):
        sig = SignalResult()
        assert sig.action == "hold"
        assert sig.direction == ""
        assert sig.stop_price == 0.0
        assert sig.confidence == 0.0

    def test_buy_signal(self):
        sig = SignalResult(
            action="buy",
            direction="long",
            stop_price=95.0,
            target_price=110.0,
            confidence=0.8,
        )
        assert sig.action == "buy"
        assert sig.direction == "long"
        assert sig.stop_price == 95.0
        assert sig.target_price == 110.0

    def test_metadata_defaults_to_empty_dict(self):
        sig = SignalResult()
        assert sig.metadata == {}
        # New instances shouldn't share the same dict
        sig2 = SignalResult()
        sig2.metadata["key"] = "value"
        assert SignalResult().metadata == {}


class TestStrategyMeta:
    def test_creation(self):
        meta = StrategyMeta(
            name="test_strategy",
            variant=DataMode.REAL,
            description="A test strategy",
            required_indicators=["rsi_14", "sma_20"],
            params={"period": 14},
        )
        assert meta.name == "test_strategy"
        assert meta.variant == DataMode.REAL
        assert meta.required_indicators == ["rsi_14", "sma_20"]
        assert meta.params == {"period": 14}

    def test_frozen(self):
        meta = StrategyMeta(
            name="test",
            variant=DataMode.PROXY,
            description="x",
            required_indicators=[],
        )
        try:
            meta.name = "changed"  # type: ignore
            assert False, "Should have raised FrozenInstanceError"
        except Exception:
            pass


class TestDataMode:
    def test_values(self):
        assert DataMode.PROXY.value == "proxy"
        assert DataMode.REAL.value == "real"
