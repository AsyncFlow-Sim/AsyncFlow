"""
Runtime resource registry for server nodes.

This module defines the ResourcesRuntime class, which takes a validated
TopologyGraph and a SimPy environment, then builds and stores a map
from each server's unique identifier to its SimPy resource containers.
Processes can later retrieve CPU and RAM containers by indexing this registry.
"""

import simpy

from asyncflow.resources.server_containers import ServerContainers, build_containers
from asyncflow.schemas.topology.graph import TopologyGraph


class ResourcesRuntime:
    """definition of the class to associate resources to various nodes"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        data: TopologyGraph,

    ) -> None:
        """Initialization of the attributes"""
        self.env = env
        self.data = data
        self._by_server: dict[str, ServerContainers] = {
            server.id: build_containers(env, server.server_resources)
            for server in data.nodes.servers
        }

    def __getitem__(self, server_id: str) -> ServerContainers:
        """
        Useful map to pass to each server the resources based
        on the server unique id
        """
        return self._by_server[server_id]
