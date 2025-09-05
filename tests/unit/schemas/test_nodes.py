"""
Unit tests for node schemas:
- NodesResources
- Client
- Server
- LoadBalancer
- TopologyNodes
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asyncflow.config.constants import (
    EndpointStepCPU,
    LbAlgorithmsName,
    NodesResourcesDefaults,
    StepOperation,
    SystemNodes,
)
from asyncflow.schemas.topology.endpoint import Endpoint, Step
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    NodesResources,
    Server,
    TopologyNodes,
)

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _dummy_endpoint() -> Endpoint:
    """Return a minimal valid endpoint with one CPU step."""
    step = Step(
        kind=EndpointStepCPU.CPU_BOUND_OPERATION,
        step_operation={StepOperation.CPU_TIME: 0.01},
    )
    return Endpoint(endpoint_name="/ping", steps=[step])


def _one_server_topology() -> TopologyNodes:
    """Build a minimal topology with one client and one server."""
    cli = Client(id="cli-1", type=SystemNodes.CLIENT)
    srv = Server(
        id="srv-1",
        type=SystemNodes.SERVER,
        server_resources=NodesResources(),
        endpoints=[_dummy_endpoint()],
    )
    return TopologyNodes(servers=[srv], client=cli)


# --------------------------------------------------------------------------- #
# NodesResources                                                               #
# --------------------------------------------------------------------------- #


def test_nodes_resources_defaults_match_constants() -> None:
    """Defaults match NodesResourcesDefaults constants."""
    res = NodesResources()
    assert res.cpu_cores == NodesResourcesDefaults.CPU_CORES
    assert res.ram_mb == NodesResourcesDefaults.RAM_MB
    assert res.db_connection_pool is NodesResourcesDefaults.DB_CONNECTION_POOL


def test_nodes_resources_minimum_constraints() -> None:
    """Values below minimum bounds raise ValidationError."""
    with pytest.raises(ValidationError):
        NodesResources(cpu_cores=0, ram_mb=NodesResourcesDefaults.RAM_MB)
    with pytest.raises(ValidationError):
        NodesResources(
            cpu_cores=NodesResourcesDefaults.CPU_CORES,
            ram_mb=NodesResourcesDefaults.MINIMUM_RAM_MB - 1,
        )


# --------------------------------------------------------------------------- #
# Client                                                                       #
# --------------------------------------------------------------------------- #


def test_client_type_must_be_client() -> None:
    """Client.type must equal SystemNodes.CLIENT."""
    cli = Client(id="c1", type=SystemNodes.CLIENT)
    assert cli.type is SystemNodes.CLIENT

    with pytest.raises(ValidationError):
        Client(id="bad", type=SystemNodes.SERVER)


def test_client_ram_per_process_requires_resources() -> None:
    """If ram_per_process is set, client_resources must be provided."""
    with pytest.raises(ValidationError):
        Client(id="c1", ram_per_process=64)

    ok = Client(
        id="c2",
        client_resources=NodesResources(ram_mb=2048),
        ram_per_process=64,
    )
    assert ok.client_resources is not None


# --------------------------------------------------------------------------- #
# Server                                                                       #
# --------------------------------------------------------------------------- #


def test_server_type_must_be_server() -> None:
    """Server.type must equal SystemNodes.SERVER."""
    srv = Server(
        id="s1",
        type=SystemNodes.SERVER,
        server_resources=NodesResources(),
        endpoints=[_dummy_endpoint()],
    )
    assert srv.type is SystemNodes.SERVER

    with pytest.raises(ValidationError):
        Server(
            id="bad",
            type=SystemNodes.CLIENT,
            server_resources=NodesResources(),
            endpoints=[_dummy_endpoint()],
        )


def test_server_requires_at_least_one_endpoint() -> None:
    """Endpoints list must be non-empty."""
    with pytest.raises(ValidationError):
        Server(
            id="s1",
            server_resources=NodesResources(),
            endpoints=[],
        )


# --------------------------------------------------------------------------- #
# LoadBalancer                                                                 #
# --------------------------------------------------------------------------- #


def test_load_balancer_type_and_defaults() -> None:
    """LB.type and default algorithm validate."""
    lb = LoadBalancer(id="lb1", type=SystemNodes.LOAD_BALANCER)
    assert lb.type is SystemNodes.LOAD_BALANCER
    assert lb.algorithms is LbAlgorithmsName.ROUND_ROBIN


def test_lb_ram_per_process_requires_resources() -> None:
    """If ram_per_process is set, lb_resources must be provided."""
    with pytest.raises(ValidationError):
        LoadBalancer(
            id="lb1",
            ram_per_process=64,
        )

    ok = LoadBalancer(
        id="lb2",
        lb_resources=NodesResources(ram_mb=2048),
        ram_per_process=64,
    )
    assert ok.lb_resources is not None


# --------------------------------------------------------------------------- #
# TopologyNodes                                                                #
# --------------------------------------------------------------------------- #


def test_topology_nodes_unique_ids_validator() -> None:
    """Duplicate node IDs are rejected."""
    topo = _one_server_topology()
    dup_srv = topo.servers[0].model_copy(update={"id": "cli-1"})
    with pytest.raises(ValidationError):
        TopologyNodes(servers=[dup_srv], client=topo.client)


def test_topology_lb_references_unknown_server_fails() -> None:
    """LB must only cover servers present in the topology."""
    topo = _one_server_topology()
    lb = LoadBalancer(id="lb-1", server_covered={"missing"})
    with pytest.raises(ValidationError):
        TopologyNodes(
            servers=topo.servers,
            client=topo.client,
            load_balancer=lb,
        )


def test_topology_lb_with_valid_coverage_passes() -> None:
    """LB covering an existing server validates."""
    topo = _one_server_topology()
    lb = LoadBalancer(id="lb-1", server_covered={"srv-1"})
    ok = TopologyNodes(
        servers=topo.servers,
        client=topo.client,
        load_balancer=lb,
    )
    assert ok.load_balancer is not None
    assert ok.load_balancer.server_covered == {"srv-1"}


def test_topology_server_ram_per_process_total_lt_ram() -> None:
    """Total per-process RAM must be strictly less than node RAM."""
    srv = Server(
        id="s1",
        server_resources=NodesResources(cpu_cores=2, ram_mb=1024),
        endpoints=[_dummy_endpoint()],
        ram_per_process=200,
    )
    topo = TopologyNodes(servers=[srv], client=Client(id="c1"))
    assert topo.servers[0].ram_per_process == 200

    # Now violate the constraint: 2 cores * 600 >= 1024 → invalid
    bad_srv = srv.model_copy(update={"ram_per_process": 600})
    with pytest.raises(ValidationError):
        TopologyNodes(servers=[bad_srv], client=Client(id="c2"))
