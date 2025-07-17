"""
definition of the class representing the rqs generator
that will be passed as a process in the simpy simulation
"""

from __future__ import annotations

from typing import Generator, TYPE_CHECKING

import simpy

from app.config.constants import Distribution
from app.config.rqs_state import RequestState
from app.core.event_samplers.gaussian_poisson import gaussian_poisson_sampling
from app.core.event_samplers.poisson_poisson import poisson_poisson_sampling

if TYPE_CHECKING:
    from collections.abc import Generator

    import numpy as np

    from app.schemas.requests_generator_input import RqsGeneratorInput
    from app.schemas.simulation_settings_input import SimulationSettings


class RqsGeneratorRuntime():
    """
    A “node” that produces request contexts at stochastic inter‐arrival times
    and immediately pushes them down the pipeline via an EdgeRuntime.
    """
    def __init__(
        self,
        env: simpy.Environment,
        state: RequestState,
        rqs_generator_data: RqsGeneratorInput,
        sim_settings: SimulationSettings,
        *,
        rng: np.random.Generator | None = None
        ):
        
        self.rqs_generator_data = rqs_generator_data
        self.sim_settings = sim_settings
        self.rng =  rng or np.random.default_rng()
        self.state = state
        self.env = env

        
    def _requests_generator(self) -> Generator[float, None, None]:
        """
        Return an iterator of inter-arrival gaps (seconds) according to the model
        chosen in *input_data*.

        Notes
        -----
        * If ``avg_active_users.distribution`` is ``"gaussian"`` or ``"normal"``,
        the Gaussian-Poisson sampler is used.
        * Otherwise the default Poisson-Poisson sampler is returned.

        """
        dist = self.rqs_generator_data.avg_active_users.distribution.lower()

        if dist == Distribution.NORMAL:
            #Gaussian-Poisson model
            return gaussian_poisson_sampling(
                input_data=self.rqs_generator_data,
                sim_settings=self.sim_settings,
                rng=self.rng,

            )

        # Poisson + Poisson
        return poisson_poisson_sampling(
            input_data=self.rqs_generator_data,
            sim_settings=self.sim_settings,
            rng=self.rng,
        )
        
    def _event_arrival(self) -> Generator[simpy.Event, None, None]:
        """simulating the process of event generation"""
        time_gaps = self._requests_generator()
        
        for gap in time_gaps:
            yield self.env.timeout(gap)
            
    def run(self) -> simpy.Process:
        """passing the structure as a simpy process"""
        return self.env.process(self._event_arrival())