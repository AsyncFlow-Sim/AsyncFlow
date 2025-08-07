"""Unit-tests for helper-functions in
`app.core.event_samplers.common_helpers`.
"""
from __future__ import annotations

from typing import cast

import numpy as np
import pytest

from app.config.constants import Distribution
from app.samplers.common_helpers import (
    exponential_variable_generator,
    general_sampler,
    lognormal_variable_generator,
    poisson_variable_generator,
    truncated_gaussian_generator,
    uniform_variable_generator,
)
from app.schemas.random_variables_config import RVConfig

# --------------------------------------------------------------------------- #
# Dummy RNG                                                                   #
# --------------------------------------------------------------------------- #


class DummyRNG:
    """Minimal stub mimicking the subset of the NumPy RNG API used in tests."""

    def __init__(  # noqa: D107
        self,
        *,
        uniform_value: float | None = None,
        poisson_value: int | None = None,
        normal_value: float | None = None,
        lognormal_value: float | None = None,
        exponential_value: float | None = None,
    ) -> None:
        self.uniform_value = uniform_value
        self.poisson_value = poisson_value
        self.normal_value = normal_value
        self.lognormal_value = lognormal_value
        self.exponential_value = exponential_value

    # --- uniform ----------------------------------------------------------- #

    def random(self) -> float:
        """Return the preset ``uniform_value`` or fall back to a real RNG."""
        if self.uniform_value is not None:
            return self.uniform_value
        return float(np.random.default_rng().random())

    # --- Poisson ----------------------------------------------------------- #

    def poisson(self, lam: float) -> int:
        """Return the preset ``poisson_value`` or draw from a real Poisson."""
        if self.poisson_value is not None:
            return self.poisson_value
        return int(np.random.default_rng().poisson(lam))

    # --- Normal ------------------------------------------------------------ #

    def normal(self, mean: float, sigma: float) -> float:
        """Return the preset ``normal_value`` or draw from a real Normal."""
        if self.normal_value is not None:
            return self.normal_value
        return float(np.random.default_rng().normal(mean, sigma))

    # --- Log-normal -------------------------------------------------------- #

    def lognormal(self, mean: float, sigma: float) -> float:
        """Return the preset ``lognormal_value`` or draw from a real LogNormal."""
        if self.lognormal_value is not None:
            return self.lognormal_value
        return float(np.random.default_rng().lognormal(mean, sigma))

    # --- Exponential ------------------------------------------------------- #

    def exponential(self, scale: float) -> float:
        """Return the preset ``exponential_value`` or draw from a real Exponential."""
        if self.exponential_value is not None:
            return self.exponential_value
        return float(np.random.default_rng().exponential(scale))


# --------------------------------------------------------------------------- #
# Tests for low-level generators                                              #
# --------------------------------------------------------------------------- #


def test_uniform_variable_generator_with_dummy_rng() -> None:
    """`uniform_variable_generator` returns the dummy's ``uniform_value``."""
    dummy = cast("np.random.Generator", DummyRNG(uniform_value=0.75))
    assert uniform_variable_generator(dummy) == 0.75


def test_uniform_variable_generator_bounds() -> None:
    """Calling with a real RNG yields a value in the half-open interval [0, 1)."""
    rng = np.random.default_rng(1_234)
    val = uniform_variable_generator(rng)
    assert 0.0 <= val < 1.0


def test_poisson_variable_generator_with_dummy_rng() -> None:
    """`poisson_variable_generator` returns the dummy's ``poisson_value``."""
    dummy = cast("np.random.Generator", DummyRNG(poisson_value=3))
    assert poisson_variable_generator(mean=5.0, rng=dummy) == 3


def test_poisson_variable_generator_reproducible() -> None:
    """Two RNGs with the same seed produce identical Poisson draws."""
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    v1 = poisson_variable_generator(7.0, rng1)
    v2 = poisson_variable_generator(7.0, rng2)
    assert v1 == v2


def test_truncated_gaussian_generator_negative_clamped() -> None:
    """Negative Normal draws are clamped to zero."""
    dummy = cast("np.random.Generator", DummyRNG(normal_value=-2.7))
    assert truncated_gaussian_generator(10.0, 5.0, dummy) == 0.0


def test_truncated_gaussian_generator_positive_passthrough() -> None:
    """Positive Normal draws pass through unchanged."""
    dummy = cast("np.random.Generator", DummyRNG(normal_value=3.9))
    val = truncated_gaussian_generator(10.0, 5.0, dummy)
    assert isinstance(val, float)
    assert val == 3.9


def test_truncated_gaussian_generator_default_rng_non_negative() -> None:
    """Real RNG always yields a non-negative float after truncation."""
    rng = np.random.default_rng(321)
    assert truncated_gaussian_generator(10.0, 2.0, rng) >= 0.0


def test_lognormal_variable_generator_reproducible() -> None:
    """`lognormal_variable_generator` is reproducible with a fixed seed."""
    rng1 = np.random.default_rng(99)
    rng2 = np.random.default_rng(99)
    v1 = lognormal_variable_generator(1.0, 0.5, rng1)
    v2 = lognormal_variable_generator(1.0, 0.5, rng2)
    assert v1 == pytest.approx(v2)


def test_exponential_variable_generator_reproducible() -> None:
    """`exponential_variable_generator` is reproducible with a fixed seed."""
    rng1 = np.random.default_rng(54_321)
    rng2 = np.random.default_rng(54_321)
    v1 = exponential_variable_generator(2.0, rng1)
    v2 = exponential_variable_generator(2.0, rng2)
    assert v1 == pytest.approx(v2)


# --------------------------------------------------------------------------- #
# Tests for `general_sampler`                                                 #
# --------------------------------------------------------------------------- #


def test_general_sampler_uniform_path() -> None:
    """Uniform branch returns the dummy's preset value."""
    dummy = cast("np.random.Generator", DummyRNG(uniform_value=0.42))
    cfg = RVConfig(mean=1.0, distribution=Distribution.UNIFORM)
    assert general_sampler(cfg, dummy) == 0.42


def test_general_sampler_normal_path() -> None:
    """Normal branch applies truncation logic (negative → 0)."""
    dummy = cast("np.random.Generator", DummyRNG(normal_value=-1.2))
    cfg = RVConfig(mean=0.0, variance=1.0, distribution=Distribution.NORMAL)
    assert general_sampler(cfg, dummy) == 0.0


def test_general_sampler_poisson_path() -> None:
    """Poisson branch returns the dummy's preset integer as *float*."""
    dummy = cast("np.random.Generator", DummyRNG(poisson_value=4))
    cfg = RVConfig(mean=5.0, distribution=Distribution.POISSON)
    result = general_sampler(cfg, dummy)
    assert isinstance(result, float)
    assert result == 4.0


def test_general_sampler_lognormal_path() -> None:
    """Log-normal branch produces a strictly positive float."""
    rng = np.random.default_rng(2_025)
    cfg = RVConfig(mean=0.0, variance=0.5, distribution=Distribution.LOG_NORMAL)
    assert general_sampler(cfg, rng) > 0.0


def test_general_sampler_exponential_path() -> None:
    """Exponential branch produces a strictly positive float."""
    rng = np.random.default_rng(7)
    cfg = RVConfig(mean=1.5, distribution=Distribution.EXPONENTIAL)
    assert general_sampler(cfg, rng) > 0.0
