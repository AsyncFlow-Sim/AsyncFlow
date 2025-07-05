"""simulation of the server"""

from __future__ import annotations

from typing import TYPE_CHECKING

import simpy

from app.core.requests_generator import requests_generator
from app.schemas.simulation_output import SimulationOutput

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    import numpy as np

    from app.schemas.simulation_input import SimulationInput




def run_simulation(
    data: SimulationInput,
    *,
    rng: np.random.Generator,
) -> SimulationOutput:
    """
    Esegue la simulazione in SimPy usando i gap prodotti da requests_generator.
    Per ora calcola solo il numero totale di richieste arrivate.
    """
    gaps: Iterator[float] = requests_generator(data, rng=rng)
    env = simpy.Environment()

    simulation_time = data.total_simulation_time
    # pydantic in the validation assign a value and mypy is not
    # complaining because a None cannot be compared in the loop
    # to a float
    assert simulation_time is not None

    total_request_per_time_period = {
        "simulation_time": simulation_time,
        "total_requests": 0,
        }

    def arrival_process(
        env: simpy.Environment,
    ) -> Generator[simpy.events.Event, None, None]:
        for gap in gaps:
            yield env.timeout(gap)
            total_request_per_time_period["total_requests"] += 1

    env.process(arrival_process(env))
    env.run(until=simulation_time)

    return SimulationOutput(
        total_requests=total_request_per_time_period,
        metric_2=str(data.avg_request_per_minute_per_user.mean),
        metric_n=str(data.avg_active_users.mean),
    )
