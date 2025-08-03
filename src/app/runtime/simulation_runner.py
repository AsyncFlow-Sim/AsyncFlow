"""Components to run the whole simulation given specific input data"""

from typing import TYPE_CHECKING

import numpy as np
import simpy

from app.resources.registry import ResourcesRuntime
from app.runtime.actors.server import ServerRuntime
from app.schemas.full_simulation_input import SimulationPayload

if TYPE_CHECKING:
    from app.schemas.system_topology.full_system_topology import (
    Client,
    LoadBalancer,
    Server,
)



class SimulationRunner:
    """Class to handle the simulation"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        simulation_input: SimulationPayload,
        ) -> None:
        """Docstring to generate"""
        self.env = env
        self.simulation_input = simulation_input

        # instantiation of object needed to build nodes for the runtime phase
        self.servers: list[Server] = simulation_input.topology_graph.nodes.servers
        self.client: Client = simulation_input.topology_graph.nodes.client
        self.lb: LoadBalancer | None = (
            simulation_input.topology_graph.nodes.load_balancer
        )
        self.simulation_settings = simulation_input.sim_settings
        self.rng = np.random.default_rng()

        # Object needed to start the simualation
        self._servers_runtime: dict[str, ServerRuntime] = {}

    def _build_servers(self) -> dict[str, ServerRuntime]:
        """
        Build given the input data a dict containing all server Runtime
        indexed by their unique id
        """
        registry = ResourcesRuntime(
            env=self.env,
            data=self.simulation_input.topology_graph,
        )
        for server in self.servers:
            container = registry[server.id]
            self._servers_runtime[server.id] = ServerRuntime(
                env=self.env,
                server_resources=container,
                server_config=server,
                out_edge=None,
                server_box=simpy.Store(self.env),
                settings=self.simulation_settings,
                rng= self.rng,

            )
        

        return self._servers_runtime
