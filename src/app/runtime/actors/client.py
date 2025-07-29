"""defining the object client for the simulation"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import simpy

from app.config.constants import SystemNodes
from app.metrics.client import build_client_metrics
from app.runtime.actors.edge import EdgeRuntime
from app.schemas.simulation_settings_input import SimulationSettings
from app.schemas.system_topology.full_system_topology import Client

if TYPE_CHECKING:
    from app.runtime.rqs_state import RequestState



class ClientRuntime:
    """class to define the client runtime"""

    def __init__( # noqa: PLR0913
        self,
        env: simpy.Environment,
        out_edge: EdgeRuntime,
        client_box: simpy.Store,
        completed_box: simpy.Store,
        client_config: Client,
        settings: SimulationSettings,
        ) -> None:
        """Definition of attributes for the client"""
        self.env = env
        self.out_edge = out_edge
        self.client_config = client_config
        self.client_box = client_box
        self.completed_box = completed_box
        self._rqs_latencies: list[float] = []
        # list to collect the time when rqs are satisfied we need this
        # to calculate the throughput in the collector
        self._rqs_time_series: list[float] = []
        # Right now is not necessary but as we will introduce
        # non mandatory metrics we will need this structure to
        # check if we have to measure a given metric
        # right now it is not necessary because we are dealing
        # only with mandatory metrics
        self._server_enabled_metrics = build_client_metrics(
            settings.enabled_sample_metrics,
        )


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
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
                self._rqs_time_series.append(state.finish_time)
                latency = state.finish_time - state.initial_time
                self._rqs_latencies.append(latency)
                yield self.completed_box.put(state)
            else:
                self.out_edge.transport(state)

    def start(self) -> simpy.Process:
        """Initialization of the process"""
        return self.env.process(self._forwarder())

    @property
    def request_latency(self) -> list[float]:
        """
        Expose the value of the private list rqs latencies
        just for reading purpose
        """
        return self._rqs_latencies

    @property
    def rqs_time_series(self) -> list[float]:
        """
        Expose the value of the private list of the
        arrival time for each rqs just for reading purpose
        """
        return self._rqs_time_series
