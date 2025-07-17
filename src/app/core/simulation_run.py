"""simulation of the server"""

from __future__ import annotations

from typing import TYPE_CHECKING

import simpy

from app.core.helpers.requests_generator import requests_generator
from app.schemas.simulation_output import SimulationOutput

if TYPE_CHECKING:
    from collections.abc import Generator

    import numpy as np

    from app.schemas.full_simulation_input import SimulationPayload






def run_simulation(
    input_data: SimulationPayload,
    *,
    rng: np.random.Generator,
) -> SimulationOutput:
    """Simulation executor in Simpy"""
    sim_settings = input_data.sim_settings

    requests_generator_input = input_data.rqs_input

    gaps: Generator[float, None, None] = requests_generator(
        requests_generator_input,
        sim_settings,
        rng=rng)
    env = simpy.Environment()


    total_request_per_time_period = {
        "simulation_time": sim_settings.total_simulation_time,
        "total_requests": 0,
        }

    def arrival_process(
        env: simpy.Environment,
    ) -> Generator[simpy.events.Event, None, None]:
        for gap in gaps:
            yield env.timeout(gap)
            total_request_per_time_period["total_requests"] += 1

    env.process(arrival_process(env))
    env.run(until=sim_settings.total_simulation_time)

    return SimulationOutput(
        total_requests=total_request_per_time_period,
        metric_2=str(requests_generator_input.avg_request_per_minute_per_user.mean),
        metric_n=str(requests_generator_input.avg_active_users.mean),
    )
