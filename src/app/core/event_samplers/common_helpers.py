"""Helpers function for the request generator"""


import numpy as np


def uniform_variable_generator(rng: np.random.Generator | None = None) -> float:
    """Return U~Uniform(0, 1)."""
    rng = rng or np.random.default_rng()
    return float(rng.random())


def poisson_variable_generator(
    mean: float,
    rng: np.random.Generator | None = None,
) -> int:
    """Return a Poisson-distributed integer with expectation *mean*."""
    rng = rng or np.random.default_rng()
    return int(rng.poisson(mean))
