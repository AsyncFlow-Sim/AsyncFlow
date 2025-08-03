"""Components to run the whole simulation given specific input data"""

from typing import TYPE_CHECKING

import numpy as np
import simpy

from app.resources.registry import ResourcesRuntime
from app.runtime.actors.client import ClientRuntime
from app.runtime.actors.load_balancer import LoadBalancerRuntime
from app.runtime.actors.rqs_generator import RqsGeneratorRuntime
from app.runtime.actors.server import ServerRuntime
from app.schemas.full_simulation_input import SimulationPayload

if TYPE_CHECKING:
    from app.schemas.rqs_generator_input import RqsGeneratorInput
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
        """
        Orchestrates building, wiring and running all actor runtimes.

        Args:
            env (simpy.Environment): global environment for the simulation
            simulation_input (SimulationPayload): full input for the simulation

        """
        self.env = env
        self.simulation_input = simulation_input

        # instantiation of object needed to build nodes for the runtime phase
        self.servers: list[Server] = simulation_input.topology_graph.nodes.servers
        self.client: Client = simulation_input.topology_graph.nodes.client
        self.rqs_generator: RqsGeneratorInput = simulation_input.rqs_input
        self.lb: LoadBalancer | None = None
        self.simulation_settings = simulation_input.sim_settings
        self.rng = np.random.default_rng()

        # Object needed to start the simualation
        self._servers_runtime: dict[str, ServerRuntime] = {}
        self._client_runtime: dict[str, ClientRuntime] = {}
        self._rqs_runtime: dict[str, RqsGeneratorRuntime] = {}
        self._lb_runtime: dict[str, LoadBalancerRuntime] = {}

    def _make_inbox(self) -> simpy.Store:   # local helper
       """Helper to create store for the states of the simulation"""
       return simpy.Store(self.env)

    def _build_rqs_generator(self) -> dict[str, RqsGeneratorRuntime]:
        """
        Build the rqs generator runtime, we use a dict for one reason
        In the future we might add CDN so we will need
        multiple generators , one for each client
        """
        self._rqs_runtime[self.rqs_generator.id] = RqsGeneratorRuntime(
            env = self.env,
            out_edge=None,
            rqs_generator_data=self.rqs_generator,
            sim_settings=self.simulation_settings,
            rng=self.rng,
        )

        return self._rqs_runtime

    def _build_client_runtime(self) -> dict[str, ClientRuntime]:
        """
        Build the client runtime, we use a dict for two reasons
        1) In the future we might add CDN so we will need
           multiple client
        2) When we will assign outer edges we will need a dict
           with all components indexed by their id
        """
        self._client_runtime[self.client.id] = ClientRuntime(
            env=self.env,
            out_edge=None,
            completed_box=self._make_inbox(),
            client_box=self._make_inbox(),
            client_config=self.client,
        )

        return self._client_runtime

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
                server_box=self._make_inbox(),
                settings=self.simulation_settings,
                rng= self.rng,

            )
        return self._servers_runtime

    def _build_load_balancer(self) -> dict[str, LoadBalancerRuntime]:
        """
        Build given the input data the load balancer runtime we will
        use a dict because we may have multiple load balancer and we
        will be usefull to assign outer edges
        """
        assert self.simulation_input.topology_graph.nodes.load_balancer is not None
        self.lb = self.simulation_input.topology_graph.nodes.load_balancer

        self._lb_runtime[self.lb.id] = LoadBalancerRuntime(
            env=self.env,
            lb_config=self.lb,
            out_edges= None,
            lb_box=self._make_inbox(),
        )

        return self._lb_runtime



