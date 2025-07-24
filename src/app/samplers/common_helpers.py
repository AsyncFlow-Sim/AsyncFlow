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
    """Sample a number according to the distribution described in `random_variable`."""
    dist = random_variable.distribution
    mean = random_variable.mean

    match dist:
        case Distribution.UNIFORM:

            assert random_variable.variance is None
            return uniform_variable_generator(rng)

        case _:

            variance = random_variable.variance
            assert variance is not None

            match dist:
                case Distribution.NORMAL:
                    return truncated_gaussian_generator(mean, variance, rng)
                case Distribution.LOG_NORMAL:
                    return lognormal_variable_generator(mean, variance, rng)
                case Distribution.POISSON:
                    return float(poisson_variable_generator(mean, rng))
                case Distribution.EXPONENTIAL:
                    return exponential_variable_generator(mean, rng)
                case _:
                    msg = f"Unsupported distribution: {dist}"
                    raise ValueError(msg)
