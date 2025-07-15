"""
Continuous-time event sampling for the Poisson-Poisson
and Gaussian-Poisson workload model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.constants import Distribution
from app.core.event_samplers.gaussian_poisson import gaussian_poisson_sampling
from app.core.event_samplers.poisson_poisson import poisson_poisson_sampling

if TYPE_CHECKING:
    from collections.abc import Generator

    import numpy as np

    from app.schemas.requests_generator_input import RqsGeneratorInput
    from app.schemas.simulation_settings_input import SimulationSettings


def requests_generator(
    input_data: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    *,
    rng: np.random.Generator | None = None,
) -> Generator[float, None, None]:
    """
    Return an iterator of inter-arrival gaps (seconds) according to the model
    chosen in *input_data*.

    Notes
    -----
    * If ``avg_active_users.distribution`` is ``"gaussian"`` or ``"normal"``,
      the Gaussian-Poisson sampler is used.
    * Otherwise the default Poisson-Poisson sampler is returned.

    """
    dist = input_data.avg_active_users.distribution.lower()

    if dist == Distribution.NORMAL:
        #Gaussian-Poisson model
        return gaussian_poisson_sampling(
            input_data=input_data,
            sim_settings=sim_settings,
            rng=rng,

        )

    # Poisson + Poisson
    return poisson_poisson_sampling(
        input_data=input_data,
        sim_settings=sim_settings,
        rng=rng,
    )
