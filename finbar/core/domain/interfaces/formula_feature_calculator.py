"""FormulaFeatureCalculator — compute formula feature columns."""

from abc import ABC, abstractmethod
from typing import Any


class FormulaFeatureCalculator(ABC):
    """Evaluate formula expression trees to produce feature columns."""

    @abstractmethod
    def calculate(self, frame: Any, features: list[dict]) -> Any:
        """Add formula feature columns to the frame and return it."""
        ...
