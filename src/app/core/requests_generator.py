"""
Continuous-time event sampling for the Poisson-Poisson
and Gaussian-Poisson workload model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.event_samplers.poisson_poisson import poisson_poisson_sampling

if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np

    from app.schemas.simulation_input import SimulationInput


def requests_generator(
    input_data: SimulationInput,
    *,
    simulation_time: int = 3_600,
    rng: np.random.Generator | None = None,
) -> Iterator[float]:
    """
    Select and return the appropriate inter-arrival generator.

    Currently implemented:
      • Poisson + Poisson (default)
    Gaussian + Poisson will be added later.
    """
    #dist = input_data.avg_active_users.distribution.lower()

    #if dist in {"gaussian", "normal"}:
        #return

    # Default → Poisson + Poisson
    return poisson_poisson_sampling(
        input_data=input_data,
        simulation_time_second=simulation_time,
        rng=rng,
    )
