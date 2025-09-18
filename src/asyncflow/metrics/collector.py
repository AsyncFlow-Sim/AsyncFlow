"""class to centralized the the collection of time series regarding metrics"""

from collections.abc import Generator

import simpy

from asyncflow.config.constants import SampledMetricName
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.actors.server import ServerRuntime
from asyncflow.schemas.settings.simulation import SimulationSettings

# The idea for this class is to gather list of runtime objects that
# are defined in the central class to build the simulation, in this
# way we optimize the initialization of various objects reducing
# the global overhead

class SampledMetricCollector:
    """class to define a centralized object to collect sampled metrics"""

    def __init__(
        self,
        *,
        edges: list[EdgeRuntime],
        servers: list[ServerRuntime],
        env:  simpy.Environment,
        sim_settings: SimulationSettings,
        ) -> None:
        """
        Args:
            edges (list[EdgeRuntime]): list of the class EdgeRuntime
            servers (list[ServerRuntime]): list of server of the class ServerRuntime
            env (simpy.Environment): environment for the simulation
            sim_settings (SimulationSettings): general settings for the simulation

        """
        self.edges = edges
        self.servers = servers
        self.sim_settings = sim_settings
        self.env = env
        self._sample_period = sim_settings.sample_period_s


        # enum keys instance-level for mandatory sampled metrics to collect
        self._conn_key   = SampledMetricName.EDGE_CONCURRENT_CONNECTION
        self._ram_key    = SampledMetricName.RAM_IN_USE
        self._io_key     = SampledMetricName.EVENT_LOOP_IO_SLEEP
        self._ready_key  = SampledMetricName.READY_QUEUE_LEN


    def _build_time_series(self) -> Generator[simpy.Event, None, None]:
        """Function to build time series for enabled metrics"""
        while True:
            yield self.env.timeout(self._sample_period)
            for edge in self.edges:
                if self._conn_key in edge.enabled_metrics:
                    edge.enabled_metrics[self._conn_key].append(
                        edge.concurrent_connections,
                    )
            for server in self.servers:
                if all(
                    k in server.enabled_metrics
                    for k in (self._ram_key, self._io_key, self._ready_key)
                ):
                    server.enabled_metrics[self._ram_key].append(server.ram_in_use)
                    server.enabled_metrics[self._io_key].append(server.io_queue_len)
                    server.enabled_metrics[self._ready_key].append(server.ready_queue_len)



    def start(self) -> simpy.Process:
        """Definition of the process to collect sampled metrics"""
        return self.env.process(self._build_time_series())






