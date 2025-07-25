"""class to centralized the the collection of time series regarding metrics"""

from collections.abc import Generator

import simpy

from app.config.constants import SampledMetricName
from app.runtime.actors.edge import EdgeRuntime
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
        env:  simpy.Environment,
        sim_settings: SimulationSettings,
        ) -> None:
        """Docstring to complete"""
        self.edges = edges
        self.sim_settings = sim_settings
        self.env = env
        self._sample_period = sim_settings.sample_period_s

        env.process(self._build_time_series())

    def _build_time_series(self) -> Generator[simpy.Event, None, None]:
        """Function to build time series for enabled metrics"""
        connection_key = SampledMetricName.EDGE_CONCURRENT_CONNECTION
        while True:

            yield self.env.timeout(self._sample_period)

            for edge in self.edges:
                if connection_key in edge.enabled_metrics:
                    edge.enabled_metrics[connection_key].append(
                        edge.concurrent_connections,
                    )









