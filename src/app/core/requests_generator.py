"""
Continuous-time event sampling for the Poisson-Poisson
and Gaussian-Poisson workload model.
"""

from __future__ import annotations

import math
from typing import Iterator, Optional

import numpy as np
from app.schemas.simulation_input import SimulationInput

MIN_TO_SEC_CONVERSION = 60  # 1 minute → 60 s

def uniform_variable_generator(rng: Optional[np.random.Generator] = None) -> float:
    """Return U~Uniform(0, 1)."""
    rng = rng or np.random.default_rng()
    return float(rng.random())


def poisson_variable_generator(
    mean: float,
    rng: Optional[np.random.Generator] = None,
) -> int:
    """Return a Poisson-distributed integer with expectation *mean*."""
    rng = rng or np.random.default_rng()
    return int(rng.poisson(mean))


def poisson_poisson_sampling(
    input_data: SimulationInput,
    *,
    simulation_time_second: int = 3_600,
    sampling_window_s: int = MIN_TO_SEC_CONVERSION,
    rng: Optional[np.random.Generator] = None,
) -> Iterator[float]:
    """
    Yield inter-arrival gaps (seconds) for the compound Poisson–Poisson process.

    Algorithm
    ---------
    1. Every *sampling_window_s* seconds, draw
         U ~ Poisson(mean_concurrent_user).
    2. Compute the aggregate rate
         Λ = U * (mean_req_per_minute_per_user / 60)  [req/s].
    3. While inside the current window, draw gaps
         Δt ~ Exponential(Λ)   using inverse-CDF.
    4. Stop once the virtual clock exceeds *simulation_time_second*.
    """
    rng = rng or np.random.default_rng()

    # λ_u : mean concurrent users per window
    mean_concurrent_user = float(input_data.avg_active_users.mean)

    # λ_r / 60 : mean req/s per user
    mean_req_per_sec_per_user = (
        float(input_data.avg_request_per_minute_per_user.mean) / MIN_TO_SEC_CONVERSION
    )

    now = 0.0                 # virtual clock (s)
    window_end = 0.0          # end of the current user window
    lam = 0.0                 # aggregate rate Λ (req/s)

    while now < simulation_time_second:
        # (Re)sample U at the start of each window
        if now >= window_end:
            window_end = now + float(sampling_window_s)
            users = poisson_variable_generator(mean_concurrent_user, rng)
            lam = users * mean_req_per_sec_per_user

        # No users → fast-forward to next window
        if lam <= 0.0:
            now = window_end
            continue

        # Exponential gap from a protected uniform value
        u_raw = max(uniform_variable_generator(rng), 1e-15)
        delta_t = -math.log(1.0 - u_raw) / lam

        # End simulation if the next event exceeds the horizon
        if now + delta_t > simulation_time_second:
            break

        # If the gap crosses the window boundary, jump to it
        if now + delta_t >= window_end:
            now = window_end
            continue

        now += delta_t
        yield delta_t


def request_generator(
    input_data: SimulationInput,
    *,
    simulation_time: int = 3_600,
    rng: Optional[np.random.Generator] = None,
) -> Iterator[float]:
    """
    Select and return the appropriate inter-arrival generator.

    Currently implemented:
      • Poisson + Poisson (default)
    Gaussian + Poisson will be added later.
    """
    dist = input_data.avg_active_users.distribution.lower()

    if dist in {"gaussian", "normal"}:
        # TODO: implement gaussian_poisson_sampling(...)
        raise NotImplementedError("Gaussian–Poisson sampling not yet implemented")

    # Default → Poisson + Poisson
    return poisson_poisson_sampling(
        input_data=input_data,
        simulation_time_second=simulation_time,
        rng=rng,
    )
