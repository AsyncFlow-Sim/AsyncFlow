"""Definition of the input of the simulation through python object"""

from __future__ import annotations

from typing import Self

from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    Server,
    TopologyNodes,
)
from asyncflow.schemas.workload.rqs_generator import RqsGenerator


class AsyncFlow:
    """class with method to create the input for the simulation"""

    def __init__(self) -> None:
        """Instance attributes necessary to define the simulation payload"""
        self._generator: RqsGenerator | None = None
        self._client: Client | None = None
        self._servers: list[Server] | None = None
        self._edges: list[Edge] | None = None
        self._sim_settings: SimulationSettings | None = None
        self._load_balancer: LoadBalancer | None = None

    def add_generator(self, rqs_generator: RqsGenerator) -> Self:
        """Method to instantiate the generator"""
        if not isinstance(rqs_generator, RqsGenerator):
            msg = "You must add a RqsGenerator instance"
            raise TypeError(msg)
        self._generator = rqs_generator
        return self

    def add_client(self, client: Client) -> Self:
        """Method to instantiate the client"""
        if not isinstance(client, Client):
            msg = "You must add a Client instance"
            raise TypeError(msg)

        self._client = client
        return self

    def add_servers(self, *servers: Server) -> Self:
        """Method to instantiate the server list"""
        if self._servers is None:
            self._servers = []

        for server in servers:
            if not isinstance(server, Server):
                msg = "All the instances must be of the type Server"
                raise TypeError(msg)
            self._servers.append(server)
        return self

    def add_edges(self, *edges: Edge) -> Self:
        """Method to instantiate the list of edges"""
        if self._edges is None:
            self._edges = []

        for edge in edges:
            if not isinstance(edge, Edge):
                msg = "All the instances must be of the type Edge"
                raise TypeError(msg)
            self._edges.append(edge)
        return self

    def add_simulation_settings(self, sim_settings: SimulationSettings) -> Self:
        """Method to instantiate the settings for the simulation"""
        if not isinstance(sim_settings, SimulationSettings):
            msg = "The instance must be of the type SimulationSettings"
            raise TypeError(msg)

        self._sim_settings = sim_settings
        return self

    def add_load_balancer(self, load_balancer: LoadBalancer) -> Self:
        """Method to instantiate a load balancer"""
        if not isinstance(load_balancer, LoadBalancer):
            msg = "The instance must be of the type LoadBalancer"
            raise TypeError(msg)

        self._load_balancer = load_balancer
        return self

    def build_payload(self) -> SimulationPayload:
        """Method to build the payload for the simulation"""
        if self._generator is None:
            msg = "The generator input must be instantiated before the simulation"
            raise ValueError(msg)
        if self._client is None:
            msg = "The client input must be instantiated before the simulation"
            raise ValueError(msg)
        if not self._servers:
            msg = "You must instantiate at least one server before the simulation"
            raise ValueError(msg)
        if not self._edges:
            msg = "You must instantiate edges before the simulation"
            raise ValueError(msg)
        if self._sim_settings is None:
            msg = "The simulation settings must be instantiated before the simulation"
            raise ValueError(msg)

        nodes = TopologyNodes(
            servers=self._servers,
            client=self._client,
            load_balancer=self._load_balancer,
        )

        graph = TopologyGraph(
            nodes = nodes,
            edges=self._edges,
        )

        return SimulationPayload.model_validate({
            "rqs_input": self._generator,
            "topology_graph": graph,
            "sim_settings": self._sim_settings,
        })



