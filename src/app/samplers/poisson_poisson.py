"""
event sampler in the case of poisson distribution
both for concurrent user and rqs per minute per user
"""

import math
from collections.abc import Generator

import numpy as np

from app.config.constants import TimeDefaults
from app.samplers.common_helpers import (
    poisson_variable_generator,
    uniform_variable_generator,
)
from app.schemas.rqs_generator_input import RqsGeneratorInput
from app.schemas.simulation_settings_input import SimulationSettings


def poisson_poisson_sampling(
    input_data: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    *,
    rng: np.random.Generator,
) ->  Generator[float, None, None]:
    """
    Yield inter-arrival gaps (seconds) for the compound Poisson-Poisson process.

    Algorithm
    ---------
    1. Every sampling_window_s seconds, draw
         U ~ Poisson(mean_concurrent_user).
    2. Compute the aggregate rate
         Λ = U * (mean_req_per_minute_per_user / 60)  [req/s].
    3. While inside the current window, draw gaps
         Δt ~ Exponential(Λ)   using inverse-CDF.
    4. Stop once the virtual clock exceeds *total_simulation_time*.
    """
    simulation_time = sim_settings.total_simulation_time
    user_sampling_window = input_data.user_sampling_window

    # λ_u : mean concurrent users per window
    mean_concurrent_user = float(input_data.avg_active_users.mean)

    # λ_r / 60 : mean req/s per user
    mean_req_per_sec_per_user = (
        float(
            input_data.avg_request_per_minute_per_user.mean)
        / TimeDefaults.MIN_TO_SEC
    )

    now = 0.0                 # virtual clock (s)
    window_end = 0.0          # end of the current user window
    lam = 0.0                 # aggregate rate Λ (req/s)

    while now < simulation_time:
        # (Re)sample U at the start of each window
        if now >= window_end:
            window_end = now + float(user_sampling_window)
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
        if now + delta_t > simulation_time:
            break

        # If the gap crosses the window boundary, jump to it
        if now + delta_t >= window_end:
            now = window_end
            continue

        now += delta_t
        yield delta_t
