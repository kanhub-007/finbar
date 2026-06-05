"""Tests for domain entities — pure dataclasses."""

from finbar.core.domain.entities.data_mode import DataMode
from finbar.core.domain.entities.rule import Rule
from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_definition import StrategyDefinition
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


class TestRule:
    def test_creation(self):
        rule = Rule(indicator="rsi_14", operator="<", value=30)
        assert rule.indicator == "rsi_14"
        assert rule.operator == "<"
        assert rule.value == 30

    def test_string_value(self):
        rule = Rule(indicator="close", operator=">", value="sma_50")
        assert rule.value == "sma_50"


class TestStrategyDefinition:
    def test_creation(self):
        sdef = StrategyDefinition(
            name="test_strategy",
            direction="long",
            description="Test",
            entry_rules=[
                Rule(indicator="rsi_14", operator="<", value=30),
            ],
            exit_rules=[
                Rule(indicator="rsi_14", operator=">", value=70),
            ],
            stop_loss_atr_mult=2.0,
            take_profit_atr_mult=3.0,
        )
        assert sdef.name == "test_strategy"
        assert len(sdef.entry_rules) == 1
        assert len(sdef.exit_rules) == 1
        assert sdef.stop_loss_atr_mult == 2.0
        assert sdef.require_all_entry_rules is True

    def test_defaults(self):
        sdef = StrategyDefinition(name="minimal", direction="both")
        assert sdef.description == ""
        assert sdef.entry_rules == []
        assert sdef.stop_loss_atr_mult == 0.0
        assert sdef.created_at == ""
