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
        if self.step <= 0:
            return [self.min] if self.min <= self.max else []
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
        """Generate n random values within this range, snapped to the grid.

        Unlike a plain ``uniform(min, max)`` draw, each value lies on the
        declared ``step`` lattice (``min + k * step``) so random search samples
        the same parameter values as grid search. Integer steps yield
        integer-valued floats; float steps yield float values on the grid.
        """
        import random

        if self.step <= 0:
            return [self.min] * n if self.min <= self.max else []
        max_steps = int(round((self.max - self.min) / self.step))
        if max_steps < 0:
            return []
        return [
            self.min + random.randint(0, max_steps) * self.step for _ in range(n)
        ]
