"""
Inter-arrival sampling helpers (infinite generators truncated at horizon).

Each helper yields i.i.d. inter-arrival gaps (seconds) according to the
chosen family, stopping once the cumulative time would exceed `sim_time_s`.

Signatures are uniform for easier factory wiring:
- lambda_rps: mean arrival rate (req/s), must be > 0
- sim_time_s: simulation horizon in seconds (int)
- variability: VariabilityLevel or None (ignored if not applicable)
- rng: numpy Generator for reproducibility

These helpers are intended to be wired by an external public factory.
"""

from __future__ import annotations

from math import gamma, isfinite, log, sqrt
from typing import TYPE_CHECKING, Final

from asyncflow.config.constants import VariabilityLevel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from collections.abc import Generator as FloatGen

    import numpy as np

# ---- Presets and error messages -------------------------------------------

SCV_PRESETS: Final[dict[VariabilityLevel, float]] = {
    VariabilityLevel.LOW: 0.25,
    VariabilityLevel.MEDIUM: 1.0,
    VariabilityLevel.HIGH: 4.0,
}

ERR_LAMBDA_NONPOS: Final[str] = "lambda_rps must be > 0, got {value}."
ERR_UNIFORM_LOW_ONLY: Final[str] = (
    "UNIFORM supports only LOW variability in this setup."
)

PARETO_ALPHA_EPS: Final[float] = 1e-6  # ensure finite variance: alpha > 2
WEIBULL_K_LOW: Final[float] = 2.10     # hits SCV≈0.25
WEIBULL_K_MED: Final[float] = 1.0      # SCV=1 (exp)
WEIBULL_K_HIGH: Final[float] = 0.543   # hits SCV≈4

ERR_EMPTY: Final[str] = "empirical sequence is empty."
ERR_NONFINITE: Final[str] = (
    "non-finite value in {name} at index {idx}: {val!r}."
)
ERR_NO_EVENTS_AFTER_ORIGIN: Final[str] = (
    "no timestamps at or after origin; nothing to simulate."
)
ERR_NEGATIVE: Final[str] = "negative value in {name} at index {idx}: {val!r}."
ERR_MEAN_ZERO: Final[str] = (
    "mean inter-arrival is zero; cannot rescale to target rate."
)


# ---- Utilities -------------------------------------------------------------


def _iid_to_horizon(
    *,
    draw_one: Callable[[], float],   # <-- non 'callable'
    sim_time_s: int,
) -> FloatGen[float, None, None]:
    """
    Yield i.i.d. gaps from `draw_one` until the horizon would be exceeded.

    The last draw is dropped if it would push the virtual clock past
    `sim_time_s`.
    """
    now = 0.0
    while True:
        delta = float(draw_one())
        if now + delta > float(sim_time_s):
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
        return WEIBULL_K_LOW
    if level is VariabilityLevel.MEDIUM:
        return WEIBULL_K_MED
    return WEIBULL_K_HIGH  # HIGH


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

    The first yielded gap is (t0 - origin_s), then (t1 - t0), ..., (tn - t{n-1}).
    Timestamps earlier than `origin_s` are discarded.

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
            raise ValueError(ERR_NONFINITE.format(idx=i, val=v))
        ts.append(float(v))
    if not ts:
        raise ValueError(ERR_EMPTY)

    if not assume_sorted:
        ts.sort()

    # Keep only timestamps at or after the origin
    ts = [t for t in ts if t >= origin_s]
    if not ts:
        raise ValueError(ERR_NO_EVENTS_AFTER_ORIGIN)

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
    sim_time_s: int,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Exponential inter-arrivals with mean 1 / lambda_rps (SCV fixed to 1).

    `variability` is ignored.
    """
    scale = 1.0 / lambda_rps
    return _iid_to_horizon(
        draw_one=lambda: rng.exponential(scale=scale),
        sim_time_s=sim_time_s,
    )

def _poisson_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Alias for exponential inter-arrivals of a homogeneous Poisson process.

    `variability` is ignored.
    """
    return _exponential_interarrivals(
        lambda_rps=lambda_rps,
        sim_time_s=sim_time_s,
        rng=rng,
    )

def _deterministic_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,

    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Deterministic inter-arrivals with period 1 / lambda_rps (SCV = 0).

    `variability` is ignored.
    """
    _ = rng  # kept for signature uniformity
    value = 1.0 / lambda_rps
    return _iid_to_horizon(draw_one=lambda: value, sim_time_s=sim_time_s)


def _lognormal_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,
    variability: VariabilityLevel | None,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """Lognormal inter-arrivals tuned by SCV presets"""
    assert variability is not None

    c2 = SCV_PRESETS[variability]
    sigma = sqrt(log(1.0 + c2))
    mu = log(1.0 / lambda_rps) - 0.5 * sigma * sigma
    return _iid_to_horizon(
        draw_one=lambda: rng.lognormal(mean=mu, sigma=sigma),
        sim_time_s=sim_time_s,
    )

def _weibull_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,
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
        sim_time_s=sim_time_s,
    )


def _pareto_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,
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
    alpha = max(alpha, 2.0 + PARETO_ALPHA_EPS)
    x_m = (alpha - 1.0) / (alpha * lambda_rps)
    return _iid_to_horizon(
        draw_one=lambda: x_m * (rng.pareto(a=alpha) + 1.0),
        sim_time_s=sim_time_s,
    )


def _erlang_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,
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
        sim_time_s=sim_time_s,
    )

def _uniform_interarrivals(
    *,
    lambda_rps: float,
    sim_time_s: int,
    variability: VariabilityLevel | None,
    rng: np.random.Generator,
) -> FloatGen[float, None, None]:
    """
    Uniform[a, b] inter-arrivals tuned by LOW variability (only).

    Let w = sqrt(3 * c2), mu = 1 / lambda, then:
      a = mu * (1 - w), b = mu * (1 + w)
    """
    assert variability is not None

    if variability is not VariabilityLevel.LOW:
        raise ValueError(ERR_UNIFORM_LOW_ONLY)
    c2 = SCV_PRESETS[variability]
    w = sqrt(3.0 * c2)
    mu = 1.0 / lambda_rps
    a = max(mu * (1.0 - w), 0.0)
    b = mu * (1.0 + w)
    return _iid_to_horizon(
        draw_one=lambda: rng.uniform(low=a, high=b),
        sim_time_s=sim_time_s,
    )



