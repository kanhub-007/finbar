"""ParamRange entity for grid search parameter ranges."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParamRange:
    """A parameter range for grid search optimization.

    For integer parameters (fast_period), step should be an integer.
    For float parameters (stop_atr_mult), step may be a float.
    """

    min: float
    """Minimum value (inclusive)."""

    max: float
    """Maximum value (inclusive)."""

    step: float
    """Step size between values."""

    def values(self) -> list[float]:
        """Generate all grid values for this range."""
        result: list[float] = []
        current = self.min
        while current <= self.max + (self.step * 0.001):
            result.append(current)
            current += self.step
        return result

    def count(self) -> int:
        """Return the number of grid values."""
        return len(self.values())

    def random_values(self, n: int) -> list[float]:
        """Generate n random values within this range."""
        import random

        if self.step == int(self.step):
            return [
                float(random.randint(int(self.min), int(self.max))) for _ in range(n)
            ]
        return [round(random.uniform(self.min, self.max), 2) for _ in range(n)]
