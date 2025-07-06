"""
event sampler in the case of poisson distribution
both for concurrent user and rqs per minute per user
"""

import math
from collections.abc import Generator

import numpy as np

from app.config.constants import TimeDefaults
from app.core.event_samplers.common_helpers import (
    poisson_variable_generator,
    uniform_variable_generator,
)
from app.schemas.simulation_input import SimulationInput


def poisson_poisson_sampling(
    input_data: SimulationInput,
    *,
    sampling_window_s: int = TimeDefaults.SAMPLING_WINDOW.value,
    rng: np.random.Generator | None = None,
) ->  Generator[float, None, None]:
    """
    Yield inter-arrival gaps (seconds) for the compound Poisson-Poisson process.

    Algorithm
    ---------
    1. Every *sampling_window_s* seconds, draw
         U ~ Poisson(mean_concurrent_user).
    2. Compute the aggregate rate
         Λ = U * (mean_req_per_minute_per_user / 60)  [req/s].
    3. While inside the current window, draw gaps
         Δt ~ Exponential(Λ)   using inverse-CDF.
    4. Stop once the virtual clock exceeds *simulation_time*.
    """
    rng = rng or np.random.default_rng()

    simulation_time = input_data.total_simulation_time
    # pydantic in the validation assign a value and mypy is not
    # complaining because a None cannot be compared in the loop
    # to a float
    assert simulation_time is not None

    # λ_u : mean concurrent users per window
    mean_concurrent_user = float(input_data.avg_active_users.mean)

    # λ_r / 60 : mean req/s per user
    mean_req_per_sec_per_user = (
        float(
            input_data.avg_request_per_minute_per_user.mean)
        / TimeDefaults.MIN_TO_SEC.value
    )

    now = 0.0                 # virtual clock (s)
    window_end = 0.0          # end of the current user window
    Lambda = 0.0                 # aggregate rate Λ (req/s)

    while now < simulation_time:
        # (Re)sample U at the start of each window
        if now >= window_end:
            window_end = now + float(sampling_window_s)
            users = poisson_variable_generator(mean_concurrent_user, rng)
            Lambda = users * mean_req_per_sec_per_user

        # No users → fast-forward to next window
        if Lambda <= 0.0:
            now = window_end
            continue

        # Exponential gap from a protected uniform value
        u_raw = max(uniform_variable_generator(rng), 1e-15)
        delta_t = -math.log(1.0 - u_raw) / Lambda

        # End simulation if the next event exceeds the horizon
        if now + delta_t > simulation_time:
            break

        # If the gap crosses the window boundary, jump to it
        if now + delta_t >= window_end:
            now = window_end
            continue

        now += delta_t
        yield delta_t
