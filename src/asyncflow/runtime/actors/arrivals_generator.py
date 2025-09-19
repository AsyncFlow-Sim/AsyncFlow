"""
definition of the class representing the rqs generator
that will be passed as a process in the simpy simulation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from asyncflow.config.enums import SystemNodes
from asyncflow.metrics.client import RqsClock
from asyncflow.runtime.rqs_state import RequestState
from asyncflow.samplers.arrivals import general_interarrivals

if TYPE_CHECKING:

    from collections.abc import Generator

    import simpy

    from asyncflow.runtime.actors.edge import EdgeRuntime
    from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
    from asyncflow.schemas.settings.simulation import SimulationSettings

class ArrivalsGeneratorRuntime:
    """
    A node that produces request contexts at stochastic inter-arrival times
    and immediately pushes them down the pipeline via an EdgeRuntime.
    """

    def __init__( # noqa: PLR0913
        self,
        *,
        env: simpy.Environment,
        out_edge: EdgeRuntime | None,
        arrivals: ArrivalsGenerator,
        sim_settings: SimulationSettings,
        rng: np.random.Generator | None = None,
        arrivals_generator_box: simpy.Store,
        completed_box: simpy.Store,
        ) -> None:
        """
        Definition of the instance attributes for the ArrivalsGeneratorRuntime

        Args:
            env (simpy.Environment): environment for the simulation
            out_edge (EdgeRuntime): edge connecting this node with the next one
            arrivals (ArrivalsGenerator): data do define the sampler
            sim_settings (SimulationSettings): settings to start the simulation
            rng (np.random.Generator | None, optional): random variable generator.
            arrivals_generator_box: simpy box to collect request when they come back
            completed_box: box to collect all satisfied requests

        """
        self.arrivals = arrivals
        self.sim_settings = sim_settings
        self.rng =  rng or np.random.default_rng()
        self.out_edge = out_edge
        self.env = env
        self.arrivals_generator_box = arrivals_generator_box
        self.completed_box = completed_box
        self.id_counter = 0
        self._rqs_clock: list[RqsClock] = []


    def _next_id(self) -> int:
        self.id_counter += 1
        return self.id_counter


    def _event_arrival(self) -> Generator[simpy.Event, None, None]:
        """Simulating the process of event generation"""
        assert self.out_edge is not None

        time_gaps = general_interarrivals(
          simulation_time_s=self.sim_settings.total_simulation_time,
          rng=self.rng,
          arrivals=self.arrivals,
        )

        for gap in time_gaps:
            yield self.env.timeout(gap)

            state = RequestState(
                id=self._next_id(),
                initial_time=self.env.now,

            )
            state.record_hop(
                SystemNodes.GENERATOR,
                self.arrivals.id,
                self.env.now,
            )
            # transport is a method of the edge runtime
            # which define the step of how the state is moving
            # from one node to another
            self.out_edge.transport(state)

    def _collector(self) -> Generator[simpy.Event, None, None]:
        """The request has been satisfied"""
        while True:
            state: RequestState = yield self.arrivals_generator_box.get()  # type: ignore[assignment]

            state.finish_time = self.env.now
            clock_data = RqsClock(
                start=state.initial_time,
                finish=state.finish_time,
            )
            self._rqs_clock.append(clock_data)
            yield self.completed_box.put(state)


    def start(self) -> simpy.Process:
        """Passing the structure as a simpy process"""
        self.env.process(self._event_arrival())
        self.env.process(self._collector())



    @property
    def rqs_clock(self) -> list[RqsClock]:
        """Readable version to compute aggregate metrics"""
        return self._rqs_clock
