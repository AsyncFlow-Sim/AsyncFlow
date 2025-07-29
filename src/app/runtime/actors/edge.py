"""
Unidirectional link that simulates message transmission between nodes.
Encapsulates network behavior—latency sampling (LogNormal, Exponential, etc.),
drop probability, and optional connection-pool contention—by exposing a
`send(msg)` method. Each `send` call schedules a SimPy subprocess that
waits the sampled delay (and any resource wait) before delivering the
message to the target node's inbox.
"""
from collections.abc import Generator
from typing import TYPE_CHECKING

import numpy as np
import simpy

from app.config.constants import SampledMetricName, SystemEdges
from app.metrics.edge import build_edge_metrics
from app.runtime.rqs_state import RequestState
from app.samplers.common_helpers import general_sampler
from app.schemas.simulation_settings_input import SimulationSettings
from app.schemas.system_topology.full_system_topology import Edge

if TYPE_CHECKING:
    from app.schemas.random_variables_config import RVConfig



class EdgeRuntime:
    """definining the logic to handle the edges during the simulation"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        edge_config: Edge,
        rng: np.random.Generator | None = None,
        target_box: simpy.Store,
        settings: SimulationSettings,
        ) -> None:
        """Definition of the instance attributes"""
        self.env = env
        self.edge_config = edge_config
        self.target_box = target_box
        self.rng = rng or np.random.default_rng()
        self.setting = settings
        self._edge_enabled_metrics = build_edge_metrics(
            settings.enabled_sample_metrics,
        )
        self._concurrent_connections: int = 0

        # We keep a reference to `settings` because this class needs to observe but not
        # persist the edge-related metrics the user has enabled.
        # The actual persistence (appending snapshots to the time series lists)
        # is handled centrally in metrics/collector.py,which runs every Xmilliseconds.
        # Here we only expose the current metric values, guarded by a few if checks to
        # verify that each optional metric is active. For deafult metric settings
        # is not needed but as we will scale as explained above we will need it

    def _deliver(self, state: RequestState) -> Generator[simpy.Event, None, None]:
        """Function to deliver the state to the next node"""
        # extract the random variables defining the latency of the edge
        random_variable: RVConfig = self.edge_config.latency

        uniform_variable = self.rng.uniform()
        if uniform_variable < self.edge_config.dropout_rate:
            state.finish_time = self.env.now
            state.record_hop(
                SystemEdges.NETWORK_CONNECTION,
                f"{self.edge_config.id}-dropped",
                state.finish_time,
            )
            return

        self._concurrent_connections +=1

        transit_time = general_sampler(random_variable, self.rng)
        yield self.env.timeout(transit_time)

        state.record_hop(
            SystemEdges.NETWORK_CONNECTION,
            self.edge_config.id,
            self.env.now,
            )
        self._concurrent_connections -=1
        yield self.target_box.put(state)


    def transport(self, state: RequestState) -> simpy.Process:
        """
        Called by the upstream node. Immediately spins off a SimPy process
        that will handle drop + delay + delivery of `state`.
        """
        return self.env.process(self._deliver(state))

    @property
    def enabled_metrics(self) -> dict[SampledMetricName, list[float | int]]:
        """Read-only access to the metric store."""
        return self._edge_enabled_metrics

    @property
    def concurrent_connections(self) -> int:
        """Current number of open connections on this edge."""
        return self._concurrent_connections




