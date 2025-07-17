"""Unit-tests for the **topology schemas** (Client, ServerResources, …).

Every section below is grouped by the object under test, separated by
clear comment banners so that long files remain navigable.

The tests aim for:
* 100 % branch-coverage on custom validators.
* mypy strict-compatibility (full type hints, no Any).
* ruff compliance (imports ordered, no unused vars, ≤ 88-char lines).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.constants import (
    EndpointStepCPU,
    StepOperation,
    ServerResourcesDefaults,
    SystemEdges,
    SystemNodes,
)
from app.schemas.random_variables_config import RVConfig
from app.schemas.system_topology_schema.endpoint_schema import Endpoint, Step
from app.schemas.system_topology_schema.full_system_topology_schema import (
    Client,
    Edge,
    Server,
    ServerResources,
    TopologyGraph,
    TopologyNodes,
)


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
def test_valid_client() -> None:
    """A client with correct `type` should validate."""
    cli = Client(id="frontend", type=SystemNodes.CLIENT)
    assert cli.type is SystemNodes.CLIENT


def test_invalid_client_type() -> None:
    """Wrong `type` enum on Client must raise ValidationError."""
    with pytest.raises(ValidationError):
        Client(id="wrong", type=SystemNodes.SERVER)


# --------------------------------------------------------------------------- #
# ServerResources
# --------------------------------------------------------------------------- #
def test_server_resources_defaults() -> None:
    """Default values must match the constant table."""
    res = ServerResources()  # all defaults
    assert res.cpu_cores == ServerResourcesDefaults.CPU_CORES
    assert res.ram_mb == ServerResourcesDefaults.RAM_MB
    assert res.db_connection_pool is ServerResourcesDefaults.DB_CONNECTION_POOL


def test_server_resources_min_constraints() -> None:
    """cpu_cores and ram_mb < minimum should fail validation."""
    with pytest.raises(ValidationError):
        ServerResources(cpu_cores=0, ram_mb=128)  # too small


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #
def _dummy_endpoint() -> Endpoint:
    """Return a minimal valid Endpoint needed to build a Server."""
    step = Step(
        kind=EndpointStepCPU.CPU_BOUND_OPERATION,
        step_operation={StepOperation.CPU_TIME: 0.1},
    )
    return Endpoint(endpoint_name="/ping", steps=[step])


def test_valid_server() -> None:
    """Server with correct type, resources and endpoint list."""
    srv = Server(
        id="api-1",
        type=SystemNodes.SERVER,
        server_resources=ServerResources(cpu_cores=2, ram_mb=1024),
        endpoints=[_dummy_endpoint()],
    )
    assert srv.id == "api-1"


def test_invalid_server_type() -> None:
    """Server with wrong `type` enum must be rejected."""
    with pytest.raises(ValidationError):
        Server(
            id="oops",
            type=SystemNodes.CLIENT,
            server_resources=ServerResources(),
            endpoints=[_dummy_endpoint()],
        )


# --------------------------------------------------------------------------- #
# TopologyNodes
# --------------------------------------------------------------------------- #
def _single_node_topology() -> TopologyNodes:
    """Helper that returns a valid TopologyNodes with one server and one client."""
    srv = Server(
        id="svc-A",
        server_resources=ServerResources(),
        endpoints=[_dummy_endpoint()],
    )
    cli = Client(id="browser")
    return TopologyNodes(servers=[srv], client=cli)


def test_unique_ids_validator() -> None:
    """Duplicate node IDs should trigger the unique_ids validator."""
    nodes = _single_node_topology()
    # duplicate client ID
    dup_srv = nodes.servers[0].model_copy(update={"id": "browser"})
    with pytest.raises(ValidationError):
        TopologyNodes(servers=[dup_srv], client=nodes.client)


# --------------------------------------------------------------------------- #
# Edge
# --------------------------------------------------------------------------- #
def test_edge_source_equals_target_fails() -> None:
    """Edge with identical source/target must raise."""
    latency_cfg = RVConfig(mean=0.05)
    with pytest.raises(ValidationError):
        Edge(
            source="same",
            target="same",
            latency=latency_cfg,
            edge_type=SystemEdges.NETWORK_CONNECTION,
        )


# --------------------------------------------------------------------------- #
# TopologyGraph
# --------------------------------------------------------------------------- #
def _latency() -> RVConfig:
    """A tiny helper for RVConfig latency objects."""
    return RVConfig(mean=0.02)


def test_valid_topology_graph() -> None:
    """End-to-end happy-path graph passes validation."""
    nodes = _single_node_topology()
    edge = Edge(
        source="browser",
        target="svc-A",
        latency=_latency(),
        probability=1.0,
    )
    graph = TopologyGraph(nodes=nodes, edges=[edge])
    assert len(graph.edges) == 1


def test_edge_refers_unknown_node() -> None:
    """Edge pointing to a non-existent node ID must fail."""
    nodes = _single_node_topology()
    bad_edge = Edge(
        source="browser",
        target="ghost-srv",
        latency=_latency(),
    )
    with pytest.raises(ValidationError):
        TopologyGraph(nodes=nodes, edges=[bad_edge])
