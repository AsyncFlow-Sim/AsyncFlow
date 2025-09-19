"""class to centralized the the collection of time series regarding metrics"""

from collections.abc import Generator

import simpy

from asyncflow.config.enums import LbAlgorithmsName, SampledMetricName
from asyncflow.runtime.actors.arrivals_generator import ArrivalsGeneratorRuntime
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.actors.load_balancer import LoadBalancerRuntime
from asyncflow.runtime.actors.server import ServerRuntime
from asyncflow.schemas.settings.simulation import SimulationSettings

# The idea for this class is to gather list of runtime objects that
# are defined in the central class to build the simulation, in this
# way we optimize the initialization of various objects reducing
# the global overhead

class SampledMetricCollector:
    """class to define a centralized object to collect sampled metrics"""

    def __init__(# noqa: PLR0913
        self,
        *,
        arrivals: ArrivalsGeneratorRuntime,
        edges: list[EdgeRuntime],
        servers: list[ServerRuntime],
        lb: LoadBalancerRuntime | None,
        env:  simpy.Environment,
        sim_settings: SimulationSettings,
        ) -> None:
        """
        Args:
            arrivals: (ArrivalsGeneratorRuntime): usefull to compute l_system
            edges (list[EdgeRuntime]): list of the class EdgeRuntime
            servers (list[ServerRuntime]): list of server of the class ServerRuntime
            lb (LoadBalancerRuntime): useful to compute Lq
            env (simpy.Environment): environment for the simulation
            sim_settings (SimulationSettings): general settings for the simulation

        """
        self.arrivals = arrivals
        self.edges = edges
        self.servers = servers
        self.lb = lb
        self.sim_settings = sim_settings
        self.env = env
        self._sample_period = sim_settings.sample_period_s


        # enum keys instance-level for mandatory sampled metrics to collect
        self._conn_key = SampledMetricName.EDGE_CONCURRENT_CONNECTION
        self._ram_key = SampledMetricName.RAM_IN_USE
        self._io_key = SampledMetricName.LQ_IO
        self._ready_key = SampledMetricName.LQ_SERVER
        self._l_system_key = SampledMetricName.L_SYSTEM
        self._lq_lb_key = SampledMetricName.LQ_LB
        self._server_utilization_key = SampledMetricName.SERVER_UTILIZATION


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
                    server.enabled_metrics[
                        self._server_utilization_key
                        ].append(server.server_utilization)

            if self._l_system_key in self.arrivals.enabled_metrics:
                self.arrivals.enabled_metrics[self._l_system_key].append(
                    float(self.arrivals.l_system),
                )

            if (self.lb is not None and
                self.lb.lb_config.algorithms == LbAlgorithmsName.FCFS):
                self.lb.enabled_metrics[self._lq_lb_key].append(self.lb.lq_lb)



    def start(self) -> None:
        """Definition of the process to collect sampled metrics"""
        self.env.process(self._build_time_series())






