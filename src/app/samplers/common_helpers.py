"""Helpers function for the request generator"""


import numpy as np

from app.config.constants import Distribution
from app.schemas.random_variables_config import RVConfig


def uniform_variable_generator(rng: np.random.Generator) -> float:
    """Return U~Uniform(0, 1)."""
    # rng is guaranteed to be a valid np.random.Generator due to the type signature.
    return rng.random()

def poisson_variable_generator(
    mean: float,
    rng: np.random.Generator,
) -> float:
    """Return a Poisson-distributed integer with expectation *mean*."""
    return rng.poisson(mean)

def truncated_gaussian_generator(
    mean: float,
    variance: float,
    rng: np.random.Generator,
) -> float:
    """
    Generate a Normal-distributed variable
    with mean and variance
    """
    value = rng.normal(mean, variance)
    return max(0.0, value)

def lognormal_variable_generator(
    mean: float,
    variance: float,
    rng: np.random.Generator,
) -> float:
    """Return a Poisson-distributed floateger with expectation *mean*."""
    return rng.lognormal(mean, variance)

def exponential_variable_generator(
    mean: float,
    rng: np.random.Generator,
) -> float:
    """Return an exponentially-distributed float with mean *mean*."""
    return float(rng.exponential(mean))

def general_sampler(random_variable: RVConfig, rng: np.random.Generator) -> float:
    """
    Draw one sample from the distribution described by *random_variable*.

    Only **Normal** and **Log-normal** require an explicit ``variance``.
    For **Uniform**, **Poisson** and **Exponential** the mean is enough.
    """
    dist  = random_variable.distribution
    mean  = random_variable.mean
    var   = random_variable.variance

    match dist:
        # ── No extra parameters needed ──────────────────────────────────
        case Distribution.UNIFORM:
            # Variance is meaningless for an ad-hoc uniform [0, 1) helper.
            assert var is None
            return uniform_variable_generator(rng)

        case Distribution.POISSON:
            # λ == mean ; numpy returns ints → cast to float for consistency
            assert var is None
            return float(poisson_variable_generator(mean, rng))

        case Distribution.EXPONENTIAL:
            # β (scale) == mean ; nothing else required
            assert var is None
            return exponential_variable_generator(mean, rng)

        # ── Distributions that *do* need a variance parameter ───────────
        case Distribution.NORMAL:
            assert var is not None
            return truncated_gaussian_generator(mean, var, rng)

        case Distribution.LOG_NORMAL:
            assert var is not None
            return lognormal_variable_generator(mean, var, rng)

        # ── Anything else is unsupported ────────────────────────────────
        case _:
            msg = f"Unsupported distribution: {dist}"
            raise ValueError(msg)
