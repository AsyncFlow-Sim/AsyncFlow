"""
Inter-arrival sampling helpers (infinite generators truncated at horizon).

Each helper yields i.i.d. inter-arrival gaps (seconds) according to the
chosen family, stopping once the cumulative time would exceed
`simulation_time_s`.

Signatures are uniform for easier factory wiring:
- lambda_rps: mean arrival rate (req/s), must be > 0
- simulation_time_s: simulation horizon in seconds (int)
- variability: VariabilityLevel or None (ignored if not applicable)
- rng: numpy Generator for reproducibility

These helpers are intended to be wired by an external public factory.
"""

from __future__ import annotations

from math import gamma, isfinite, log, sqrt
from typing import TYPE_CHECKING, Protocol

from asyncflow.config.constants import SCV_PRESETS, Tuning
from asyncflow.config.enums import Distribution, VariabilityLevel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from collections.abc import Generator as FloatGen

    import numpy as np

    from asyncflow.schemas.arrivals.generator import ArrivalsGenerator



# ---- Utilities -------------------------------------------------------------


def _iid_to_horizon(
    *,
    draw_one: Callable[[], float],
    simulation_time_s: int,
) -> FloatGen[float, None, None]:
    """
    Yield i.i.d. gaps from `draw_one` until the horizon would be exceeded.

    The last draw is dropped if it would push the virtual clock past
    `simulation_time_s`.
    """
    now = 0.0
    while True:
        delta = float(draw_one())
        if now + delta > float(simulation_time_s):
            break
        now += delta
        yield delta


def _weibull_shape_for_level(level: VariabilityLevel) -> float:
    """
    Map variability level to a Weibull shape k.

    Empirical mapping that matches SCV presets reasonably well:
    LOW → k≈2.10, MEDIUM → k=1.0, HIGH → k≈0.543.
    """
    if level is VariabilityLevel.LOW:
        return Tuning.WEIBULL_K_LOW
    if level is VariabilityLevel.MEDIUM:
        return Tuning.WEIBULL_K_MED
    return Tuning.WEIBULL_K_HIGH  # HIGH


# ---- Samplers --------------------------------------------------------------


def _build_empirical_from_timestamps(
    *,
    timestamps_s: Iterable[float],
    origin_s: float = 0.0,
    assume_sorted: bool = False,
    clamp_min_s: float = 0.0,
) -> FloatGen[float, None, None]:
    """
    Yield inter-arrival gaps from absolute timestamps, anchored at origin.

    Gaps strictly smaller than `clamp_min_s` are clamped to that threshold
    to avoid zero-length hot loops and numerical noise.
    """
    # Materialize and validate
    timestamp_s: list[float] = []
    for i, v in enumerate(timestamps_s):
        if not isfinite(v):
            msg = f"non-finite value in timestamps at index {i}: {v!r}."
            raise ValueError(msg)
        timestamp_s.append(float(v))
    if not timestamp_s:
        msg="empirical sequence is empty."
        raise ValueError(msg)

    if not assume_sorted:
        timestamp_s.sort()

    # Keep only timestamps at or after the origin
    timestamp_s = [t for t in timestamp_s if t >= origin_s]
    if not timestamp_s:
        msg="no timestamps at or after origin; nothing to simulate."
        raise ValueError(msg)

    # First gap from origin, then consecutive differences
    first_gap = timestamp_s[0] - origin_s
    yield first_gap if first_gap >= clamp_min_s else float(clamp_min_s)

    prev = timestamp_s[0]
    for t in timestamp_s[1:]:
        d = t - prev
        yield d if d >= clamp_min_s else float(clamp_min_s)
        prev = t



def _exponential_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Exponential inter-arrivals with mean 1 / lambda_rps (SCV fixed to 1).

    `variability` is ignored.
    """
    scale = 1.0 / lambda_rps
    return _iid_to_horizon(
        draw_one=lambda: rng.exponential(scale=scale),
        simulation_time_s=simulation_time_s,
    )


def _poisson_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Alias for exponential inter-arrivals of a homogeneous Poisson process.

    `variability` is ignored.
    """
    return _exponential_interarrivals(
        lambda_rps=lambda_rps,
        simulation_time_s=simulation_time_s,
        rng=rng,
    )


def _deterministic_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Deterministic inter-arrivals with period 1 / lambda_rps (SCV = 0).

    `variability` is ignored.
    """
    _ = rng  # kept for signature uniformity
    value = 1.0 / lambda_rps
    return _iid_to_horizon(
        draw_one=lambda: value,
        simulation_time_s=simulation_time_s,
    )


def _lognormal_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    variability: VariabilityLevel,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """Lognormal inter-arrivals tuned by SCV presets."""
    assert variability is not None

    c2 = SCV_PRESETS[variability]
    sigma = sqrt(log(1.0 + c2))
    mu = log(1.0 / lambda_rps) - 0.5 * sigma * sigma
    return _iid_to_horizon(
        draw_one=lambda: rng.lognormal(mean=mu, sigma=sigma),
        simulation_time_s=simulation_time_s,
    )


def _weibull_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    variability: VariabilityLevel,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Weibull inter-arrivals tuned by SCV via the shape k.

    Scale is set so E[T] = 1 / lambda:
      theta = (1 / lambda) / Gamma(1 + 1/k)
    """
    assert variability is not None

    k = _weibull_shape_for_level(variability)
    theta = (1.0 / lambda_rps) / gamma(1.0 + 1.0 / k)
    return _iid_to_horizon(
        draw_one=lambda: theta * rng.weibull(a=k),
        simulation_time_s=simulation_time_s,
    )


def _pareto_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    variability: VariabilityLevel,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Pareto type-I inter-arrivals tuned by SCV (finite variance).

    With target c2:
      alpha = 1 + sqrt(1 + 1 / c2)  (forced > 2)
      x_m   = (alpha - 1) / (alpha * lambda)
    """
    assert variability is not None

    c2 = SCV_PRESETS[variability]
    alpha = 1.0 + sqrt(1.0 + 1.0 / c2)
    alpha = max(alpha, 2.0 + Tuning.PARETO_ALPHA_EPS)
    x_m = (alpha - 1.0) / (alpha * lambda_rps)
    return _iid_to_horizon(
        draw_one=lambda: x_m * (rng.pareto(a=alpha) + 1.0),
        simulation_time_s=simulation_time_s,
    )


def _erlang_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    variability: VariabilityLevel,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Erlang (Gamma with integer k) inter-arrivals tuned by SCV.

    We pick k = round(1 / c2) clamped to [1, 10]. For k=1 it reduces to Exp.
    Scale is theta = (1 / lambda) / k so that E[T] = 1 / lambda.
    """
    assert variability is not None

    c2 = SCV_PRESETS[variability]
    k_int = max(1, min(10, round(1.0 / c2)))
    theta = (1.0 / lambda_rps) / float(k_int)
    return _iid_to_horizon(
        draw_one=lambda: rng.gamma(shape=k_int, scale=theta),
        simulation_time_s=simulation_time_s,
    )


def _uniform_interarrivals(
    *,
    lambda_rps: float,
    simulation_time_s: int,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Uniform[a, b] inter-arrivals with fixed relative half-width.

    `variability` is ignored. We use a symmetric band around 1/lambda:
    mu = 1 / lambda, w = UNIFORM_REL_HALF_WIDTH
    a = mu * (1 - w), b = mu * (1 + w).
    This yields a low and bounded SCV (w^2 / 3).
    """
    mu = 1.0 / lambda_rps
    w = Tuning.UNIFORM_REL_HALF_WIDTH
    a = mu * (1.0 - w)
    b = mu * (1.0 + w)
    return _iid_to_horizon(
        draw_one=lambda: rng.uniform(low=a, high=b),
        simulation_time_s=simulation_time_s,
    )


# ------------------------------------------------------------
# Define a global function to pass the correct sampler using
# dispatch tables to avoid a lot of if else
# ------------------------------------------------------------

# ---- mypy compliance ----

class VarSampler(Protocol):
    """Sampler protocol that REQUIRES a variability level."""

    def __call__(
        self,
        *,
        lambda_rps: float,
        simulation_time_s: int,
        variability: VariabilityLevel,
        rng: np.random.Generator,
    ) -> FloatGen[float, None, None]:
        """Yield inter-arrival gaps for the given rate, horizon and RNG."""
        ...


class NoVarSampler(Protocol):
    """Sampler protocol that IGNORES variability."""

    def __call__(
        self,
        *,
        lambda_rps: float,
        simulation_time_s: int,
        rng: np.random.Generator,
    ) -> FloatGen[float, None, None]:
        """Yield inter-arrival gaps for the given rate, horizon and RNG."""
        ...


VAR_DISTRIBUTION: dict[Distribution, VarSampler] = {
    Distribution.LOG_NORMAL: _lognormal_interarrivals,
    Distribution.WEIBULL: _weibull_interarrivals,
    Distribution.PARETO: _pareto_interarrivals,
    Distribution.ERLANG: _erlang_interarrivals,
}

NO_VAR_DISTRIBUTION: dict[Distribution, NoVarSampler] = {
    Distribution.EXPONENTIAL: _exponential_interarrivals,
    Distribution.POISSON: _poisson_interarrivals,
    Distribution.DETERMINISTIC: _deterministic_interarrivals,
    Distribution.UNIFORM: _uniform_interarrivals,
}

def general_interarrivals(
    *,
    simulation_time_s: int,
    rng: np.random.Generator,
    arrivals: ArrivalsGenerator,
) -> FloatGen[float, None, None]:
    """
    General function to select the correct function based on the choice
    of the user to generate interarrivals.
    """
    model = arrivals.model

    if model is Distribution.EMPIRICAL:
        if arrivals.empirical_data is None:
            msg = "empirical_data is required when model=EMPIRICAL."
            raise ValueError(msg)
        return _build_empirical_from_timestamps(
            timestamps_s=arrivals.empirical_data,
            origin_s=0.0,
            assume_sorted=False,
            clamp_min_s=0.0,
        )

    if arrivals.variability is None:
        sampler_no_var: NoVarSampler = NO_VAR_DISTRIBUTION[model]
        return sampler_no_var(
            lambda_rps=arrivals.lambda_rps,
            simulation_time_s=simulation_time_s,
            rng=rng,
        )

    sampler_var: VarSampler = VAR_DISTRIBUTION[model]
    return sampler_var(
        lambda_rps=arrivals.lambda_rps,
        simulation_time_s=simulation_time_s,
        variability=arrivals.variability,
        rng=rng,
    )


