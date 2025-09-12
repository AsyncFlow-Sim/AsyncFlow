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

from collections.abc import Callable
from collections.abc import Generator as FloatGen
from math import gamma, isfinite, log, sqrt
from typing import TYPE_CHECKING

import numpy as np

from asyncflow.config.constants import SCV_PRESETS, Tuning
from asyncflow.config.enums import Distribution, VariabilityLevel

if TYPE_CHECKING:
    from collections.abc import Iterable

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
    Yield inter-arrival gaps from absolute timestamps, anchored at `origin_s`.

    The first yielded gap is (t0 - origin_s), then (t1 - t0), ...,
    (tn - t{n-1}). Timestamps earlier than `origin_s` are discarded.

    Parameters
    ----------
    timestamps_s
        Iterable of absolute arrival times (seconds).
    origin_s
        Simulation origin in seconds. The initial idle (t0 - origin_s) is
        included as the first gap. Defaults to 0.0.
    assume_sorted
        If False, timestamps are sorted ascending. Defaults to False.
    clamp_min_s
        Minimum allowed gap; values <= 0 are replaced with this threshold to
        avoid zero-length hot loops. Defaults to 0.0.

    Yields
    ------
    float
        Inter-arrival gaps (seconds), finite sequence.

    Raises
    ------
    ValueError
        If the sequence is empty, contains non-finite values, or no timestamps
        are at/after the chosen origin.

    """
    # Materialize and validate
    ts: list[float] = []
    for i, v in enumerate(timestamps_s):
        if not isfinite(v):
            msg = (
                f"non-finite value in timestamps at index {i}: {v!r}."
            )
            raise ValueError(msg)
        ts.append(float(v))
    if not ts:
        msg = "empirical sequence is empty."
        raise ValueError(msg)

    if not assume_sorted:
        ts.sort()

    # Keep only timestamps at or after the origin
    ts = [t for t in ts if t >= origin_s]
    if not ts:
        msg = "no timestamps at or after origin; nothing to simulate."
        raise ValueError(msg)

    # First gap from origin, then consecutive differences
    first_gap = ts[0] - origin_s
    yield first_gap if first_gap > 0.0 else float(clamp_min_s)

    prev = ts[0]
    for t in ts[1:]:
        d = t - prev
        yield d if d > 0.0 else float(clamp_min_s)
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
    variability: VariabilityLevel | None,
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
    variability: VariabilityLevel | None,
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
    variability: VariabilityLevel | None,
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
    variability: VariabilityLevel | None,
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

VarSampler = Callable[
    [float, int, VariabilityLevel, np.random.Generator],
    FloatGen[float, None, None],
]

NoVarSampler = Callable[
    [float, int, np.random.Generator],
    FloatGen[float, None, None],
]

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

        # Finite generator: first gap (t0 - origin), then consecutive diffs.
        # `simulation_time_s` is not used in this branch.
        return _build_empirical_from_timestamps(
            timestamps_s=arrivals.empirical_data,
            origin_s=0.0,
            assume_sorted=False,
            clamp_min_s=0.0,
        )

    if not arrivals.variability:
        sampler = NO_VAR_DISTRIBUTION[arrivals.model]
        return sampler(
            lambda_rps=arrivals.lambda_rps,
            simulation_time_s=simulation_time_s,
            rng=rng,
        )
    sampler = VAR_DISTRIBUTION[arrivals.model]

    return sampler(
        lambda_rps=arrivals.lambda_rps,
        simulation_time_s=simulation_time_s,
        variability=arrivals.variability,
        rng=rng,
    )

