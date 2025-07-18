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

from app.config.constants import NetworkParameters
from app.config.rqs_state import RequestState
from app.core.event_samplers.common_helpers import general_sampler
from app.schemas.system_topology_schema.full_system_topology_schema import Edge

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
        ) -> None:
        """Definition of the instance attributes"""
        self.env = env
        self.edge_config = edge_config
        self.target_box = target_box
        self.rng = rng or np.random.default_rng()

    def _deliver(self, state: RequestState) -> Generator[simpy.Event, None, None]:
        """Function to deliver the state to the next node"""
        # extract the random variables defining the latency of the edge
        random_variable: RVConfig = self.edge_config.latency

        uniform_variable = self.rng.uniform()
        if uniform_variable < self.edge_config.dropout_rate:
            state.finish_time = self.env.now
            state.record_hop(f"{self.edge_config.id}-dropped", state.finish_time)
            return

        transit_time = general_sampler(random_variable, self.rng)
        yield self.env.timeout(transit_time)
        state.record_hop(self.edge_config.id, self.env.now)
        yield self.target_box.put(state)


    def transport(self, state: RequestState) -> simpy.Process:
        """
        Called by the upstream node. Immediately spins off a SimPy process
        that will handle drop + delay + delivery of `state`.
        """
        return self.env.process(self._deliver(state))






