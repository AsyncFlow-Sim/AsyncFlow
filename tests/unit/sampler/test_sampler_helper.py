from typing import cast

import numpy as np

from app.core.event_samplers.common_helpers import (
    poisson_variable_generator,
    truncated_gaussian_generator,
    uniform_variable_generator,
)


class DummyRNG:
    """Dummy RNG for testing: returns fixed values for random(), poisson(), normal()."""

    def __init__(
        self,
        uniform_value: float | None = None,
        poisson_value: int | None = None,
        normal_value: float | None = None,
    ) -> None:
        """
        Initialize the dummy RNG with optional preset outputs.

        Args:
            uniform_value: value to return from random(), if not None.
            poisson_value: value to return from poisson(), if not None.
            normal_value: value to return from normal(), if not None.

        """
        self.uniform_value = uniform_value
        self.poisson_value = poisson_value
        self.normal_value = normal_value

    def random(self) -> float:
        """
        Return the preset uniform_value or fall back to a real RNG.

        Returns:
            A float in [0.0, 1.0).

        """
        if self.uniform_value is not None:
            return self.uniform_value
        return np.random.default_rng().random()

    def poisson(self, mean: float) -> int:
        """
        Return the preset poisson_value or fall back to a real RNG.

        Args:
            mean: the λ parameter for a Poisson draw (ignored if poisson_value is set).

        Returns:
            An integer sample from a Poisson distribution.

        """
        if self.poisson_value is not None:
            return self.poisson_value
        return int(np.random.default_rng().poisson(mean))

    def normal(self, mean: float, sigma: float) -> float:
        """
        Return the preset normal_value or fall back to a real RNG.

        Args:
            mean: the mean of the Normal distribution.
            sigma: the standard deviation of the Normal distribution.

        Returns:
            A float sample from a Normal distribution.

        """
        if self.normal_value is not None:
            return self.normal_value
        return float(np.random.default_rng().normal(mean, sigma))


def test_uniform_variable_generator_with_dummy_rng() -> None:
    """Ensure uniform_variable_generator returns the dummy RNGs uniform_value."""
    dummy = cast("np.random.Generator", DummyRNG(uniform_value=0.75))
    assert uniform_variable_generator(dummy) == 0.75


def test_uniform_variable_generator_default_rng_range() -> None:
    """Ensure the default RNG produces a float in [0.0, 1.0)."""
    for _ in range(100):
        val = uniform_variable_generator()
        assert isinstance(val, float)
        assert 0.0 <= val < 1.0


def test_poisson_variable_generator_with_dummy_rng() -> None:
    """Ensure poisson_variable_generator returns the dummy RNGs poisson_value."""
    dummy = cast("np.random.Generator", DummyRNG(poisson_value=3))
    assert poisson_variable_generator(mean=5.0, rng=dummy) == 3


def test_poisson_variable_generator_reproducible() -> None:
    """Ensure two generators with the same seed produce the same Poisson sample."""
    rng1 = np.random.default_rng(12345)
    rng2 = np.random.default_rng(12345)
    v1 = poisson_variable_generator(mean=10.0, rng=rng1)
    v2 = poisson_variable_generator(mean=10.0, rng=rng2)
    assert v1 == v2


def test_truncated_gaussian_generator_truncates_negative() -> None:
    """Ensure truncated_gaussian_generator clamps negative draws to zero."""
    dummy = cast("np.random.Generator", DummyRNG(normal_value=-2.7))
    result = truncated_gaussian_generator(mean=10.0, variance=5.0, rng=dummy)
    assert result == 0


def test_truncated_gaussian_generator_truncates_toward_zero() -> None:
    """Ensure truncated_gaussian_generator rounds toward zero for positive draws."""
    dummy = cast("np.random.Generator", DummyRNG(normal_value=3.9))
    result = truncated_gaussian_generator(mean=10.0, variance=5.0, rng=dummy)
    assert isinstance(result, int)
    assert result == 3


def test_truncated_gaussian_generator_default_rng_non_negative_int() -> None:
    """
    Ensure the default RNG produces
    a non-negative integer from the truncated Gaussian.
    """
    rng = np.random.default_rng(321)
    val = truncated_gaussian_generator(mean=10.0, variance=2.0, rng=rng)
    assert isinstance(val, int)
    assert val >= 0
