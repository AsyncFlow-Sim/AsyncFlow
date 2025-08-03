"""Unit tests for ResourcesRuntime (resource registry)."""

from __future__ import annotations

import pytest
import simpy

from app.config.constants import ServerResourceName
from app.resources.registry import ResourcesRuntime
from app.schemas.system_topology.endpoint import Endpoint
from app.schemas.system_topology.full_system_topology import (
    Client,
    Server,
    ServerResources,
    TopologyGraph,
    TopologyNodes,
)


def _minimal_server(server_id: str, cores: int, ram: int) -> Server:
    """Create a Server with a dummy endpoint and resource spec."""
    res = ServerResources(cpu_cores=cores, ram_mb=ram)
    dummy_ep = Endpoint(endpoint_name="/ping", steps=[])
    return Server(id=server_id, server_resources=res, endpoints=[dummy_ep])


def _build_topology() -> TopologyGraph:
    """Return a minimal but schema-valid topology with two servers."""
    servers = [
        _minimal_server("srv-A", 2, 1024),
        _minimal_server("srv-B", 4, 2048),
    ]
    client = Client(id="clt-1")
    nodes = TopologyNodes(servers=servers, client=client)
    return TopologyGraph(nodes=nodes, edges=[])


def test_registry_initialises_filled_containers() -> None:
    """CPU and RAM containers must start full for every server."""
    env = simpy.Environment()
    topo = _build_topology()
    registry = ResourcesRuntime(env=env, data=topo)

    for srv in topo.nodes.servers:
        containers = registry[srv.id]

        cpu = containers[ServerResourceName.CPU.value]
        ram = containers[ServerResourceName.RAM.value]

        assert cpu.level == cpu.capacity == srv.server_resources.cpu_cores
        assert ram.level == ram.capacity == srv.server_resources.ram_mb


def test_getitem_unknown_server_raises_keyerror() -> None:
    """Accessing an undefined server ID should raise KeyError."""
    env = simpy.Environment()
    registry = ResourcesRuntime(env=env, data=_build_topology())

    with pytest.raises(KeyError):
        _ = registry["non-existent-server"]
