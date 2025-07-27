"""class to centralized the the collection of time series regarding metrics"""

from collections.abc import Generator

import simpy

from app.config.constants import SampledMetricName
from app.runtime.actors.edge import EdgeRuntime
from app.runtime.actors.server import ServerRuntime
from app.schemas.simulation_settings_input import SimulationSettings

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
        """Docstring to complete"""
        self.edges = edges
        self.sim_settings = sim_settings
        self.env = env
        self._sample_period = sim_settings.sample_period_s
        self.servers = servers

        # enum keys instance-level for mandatory sampled metrics to collect
        self._conn_key   = SampledMetricName.EDGE_CONCURRENT_CONNECTION
        self._ram_key    = SampledMetricName.RAM_IN_USE
        self._io_key     = SampledMetricName.EVENT_LOOP_IO_SLEEP
        self._ready_key  = SampledMetricName.READY_QUEUE_LEN
        # to add in a short period
        self._throughput = SampledMetricName.THROUGHPUT_RPS


        env.process(self._build_time_series())

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








