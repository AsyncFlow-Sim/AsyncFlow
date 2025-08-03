"""defining the object client for the simulation"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import simpy

from app.config.constants import SystemNodes
from app.metrics.client import RqsClock
from app.runtime.actors.edge import EdgeRuntime
from app.schemas.system_topology.full_system_topology import Client

if TYPE_CHECKING:
    from app.runtime.rqs_state import RequestState



class ClientRuntime:
    """class to define the client runtime"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        out_edge: EdgeRuntime | None,
        client_box: simpy.Store,
        completed_box: simpy.Store,
        client_config: Client,
        ) -> None:
        """Definition of attributes for the client"""
        self.env = env
        self.out_edge = out_edge
        self.client_config = client_config
        self.client_box = client_box
        self.completed_box = completed_box
        # This list will be enough to calculate at the end
        # of the simulation both the throughput and the
        # latency distribution

        self._rqs_clock: list[RqsClock] = []


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        assert self.out_edge is not None
        while True:
            state: RequestState = yield self.client_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.CLIENT,
                    self.client_config.id,
                    self.env.now,
                )

            # if the length of the list is bigger than two
            # it means that the state is coming back to the
            # client after being elaborated, since if the value
            # would be equal to two would mean that the state
            # went through the mandatory path to be generated
            # rqs generator and client registration
            if len(state.history) > 2:
                state.finish_time = self.env.now
                clock_data = RqsClock(
                    start=state.initial_time,
                    finish=state.finish_time,
                )
                self._rqs_clock.append(clock_data)
                yield self.completed_box.put(state)
            else:
                self.out_edge.transport(state)

    def start(self) -> simpy.Process:
        """Initialization of the process"""
        return self.env.process(self._forwarder())

    @property
    def rqs_clock(self) -> list[RqsClock]:
        """
        Expose the value of the private list of the starting
        and arrival time for each rqs just for reading purpose
        """
        return self._rqs_clock
