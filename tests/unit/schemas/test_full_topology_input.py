"""Unit-tests for topology schemas (Client, ServerResources, Edge, …)"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asyncflow.config.constants import (
    EndpointStepCPU,
    NetworkParameters,
    ServerResourcesDefaults,
    StepOperation,
    SystemEdges,
    SystemNodes,
)
from asyncflow.schemas.random_variables_config import RVConfig
from asyncflow.schemas.system_topology.endpoint import Endpoint, Step
from asyncflow.schemas.system_topology.full_system_topology import (
    Client,
    Edge,
    LoadBalancer,
    Server,
    ServerResources,
    TopologyGraph,
    TopologyNodes,
)

# --------------------------------------------------------------------------- #
# Client                                                                      #
# --------------------------------------------------------------------------- #


def test_valid_client() -> None:
    """A client with correct ``type`` validates."""
    cli = Client(id="frontend", type=SystemNodes.CLIENT)
    assert cli.type is SystemNodes.CLIENT


def test_invalid_client_type() -> None:
    """Wrong ``type`` enumeration on Client raises ValidationError."""
    with pytest.raises(ValidationError):
        Client(id="oops", type=SystemNodes.SERVER)


# --------------------------------------------------------------------------- #
# ServerResources                                                             #
# --------------------------------------------------------------------------- #


def test_server_resources_defaults() -> None:
    """All defaults match constant table."""
    res = ServerResources()
    assert res.cpu_cores == ServerResourcesDefaults.CPU_CORES
    assert res.ram_mb == ServerResourcesDefaults.RAM_MB
    assert res.db_connection_pool is ServerResourcesDefaults.DB_CONNECTION_POOL


def test_server_resources_min_constraints() -> None:
    """Values below minimum trigger validation failure."""
    with pytest.raises(ValidationError):
        ServerResources(cpu_cores=0, ram_mb=128)  # too small


# --------------------------------------------------------------------------- #
# Server                                                                      #
# --------------------------------------------------------------------------- #


def _dummy_endpoint() -> Endpoint:
    """Return a minimal valid Endpoint for Server construction."""
    step = Step(
        kind=EndpointStepCPU.CPU_BOUND_OPERATION,
        step_operation={StepOperation.CPU_TIME: 0.1},
    )
    return Endpoint(endpoint_name="/ping", steps=[step])


def test_valid_server() -> None:
    """Server with correct ``type`` and resources passes validation."""
    srv = Server(
        id="api-1",
        type=SystemNodes.SERVER,
        server_resources=ServerResources(cpu_cores=2, ram_mb=1024),
        endpoints=[_dummy_endpoint()],
    )
    assert srv.id == "api-1"


def test_invalid_server_type() -> None:
    """Server with wrong ``type`` raises ValidationError."""
    with pytest.raises(ValidationError):
        Server(
            id="bad-srv",
            type=SystemNodes.CLIENT,
            server_resources=ServerResources(),
            endpoints=[_dummy_endpoint()],
        )

# --------------------------------------------------------------------------- #
# Load Balancer                                                          #
# --------------------------------------------------------------------------- #

def test_valid_lb() -> None:
    """A LB with correct ``type`` validates."""
    cli = LoadBalancer(
        id="LB",
        type=SystemNodes.LOAD_BALANCER,
        server_covered=["s1", "s2"],
    )
    assert cli.type is SystemNodes.LOAD_BALANCER

# --------------------------------------------------------------------------- #
# TopologyNodes                                                               #
# --------------------------------------------------------------------------- #


def _single_node_topology() -> TopologyNodes:
    """Helper returning one server + one client topology."""
    srv = Server(
        id="svc-A",
        server_resources=ServerResources(),
        endpoints=[_dummy_endpoint()],
    )
    cli = Client(id="browser")
    return TopologyNodes(servers=[srv], client=cli)


def test_unique_ids_validator() -> None:
    """Duplicate node IDs trigger the ``unique_ids`` validator."""
    nodes = _single_node_topology()
    dup_srv = nodes.servers[0].model_copy(update={"id": "browser"})
    with pytest.raises(ValidationError):
        TopologyNodes(servers=[dup_srv], client=nodes.client)


# --------------------------------------------------------------------------- #
# Edge                                                                        #
# --------------------------------------------------------------------------- #


def test_edge_source_equals_target_fails() -> None:
    """Edge with identical source/target raises ValidationError."""
    latency_cfg = RVConfig(mean=0.05)
    with pytest.raises(ValidationError):
        Edge(
            id="edge-dup",
            source="same",
            target="same",
            latency=latency_cfg,
            edge_type=SystemEdges.NETWORK_CONNECTION,
        )


def test_edge_missing_id_raises() -> None:
    """Omitting mandatory ``id`` field raises ValidationError."""
    latency_cfg = RVConfig(mean=0.01)
    with pytest.raises(ValidationError):
        Edge(  # type: ignore[call-arg]
            source="a",
            target="b",
            latency=latency_cfg,
        )


@pytest.mark.parametrize(
    "bad_rate",
    [-0.1, NetworkParameters.MAX_DROPOUT_RATE + 0.1],
)
def test_edge_dropout_rate_bounds(bad_rate: float) -> None:
    """Drop-out rate outside valid range triggers ValidationError."""
    with pytest.raises(ValidationError):
        Edge(
            id="edge-bad-drop",
            source="n1",
            target="n2",
            latency=RVConfig(mean=0.01),
            dropout_rate=bad_rate,
        )


# --------------------------------------------------------------------------- #
# TopologyGraph                                                               #
# --------------------------------------------------------------------------- #


def _latency() -> RVConfig:
    """Tiny helper for latency objects."""
    return RVConfig(mean=0.02)

def _topology_with_lb(
    cover: set[str],
    extra_edges: list[Edge] | None = None,
) -> TopologyGraph:
    """Build a minimal graph with 1 client, 1 server and a load balancer."""
    nodes = _single_node_topology()
    lb = LoadBalancer(id="lb-1", server_covered=cover)
    nodes = TopologyNodes(
        servers=nodes.servers,
        client=nodes.client,
        load_balancer=lb,
    )

    edges: list[Edge] = [
        Edge(  # client -> LB
            id="cli-lb",
            source="browser",
            target="lb-1",
            latency=_latency(),
        ),
        Edge(  # LB -> server (may be removed in invalid tests)
            id="lb-srv",
            source="lb-1",
            target="svc-A",
            latency=_latency(),
        ),
    ]
    if extra_edges:
        edges.extend(extra_edges)
    return TopologyGraph(nodes=nodes, edges=edges)


def test_valid_topology_graph() -> None:
    """Happy-path graph passes validation."""
    nodes = _single_node_topology()
    edge = Edge(
        id="edge-1",
        source="browser",
        target="svc-A",
        latency=_latency(),
        probability=1.0,
    )
    graph = TopologyGraph(nodes=nodes, edges=[edge])
    assert len(graph.edges) == 1

def test_topology_graph_without_lb_still_valid() -> None:
    """Graph without load balancer validates just like before."""
    nodes = _single_node_topology()
    edge = Edge(
        id="edge-1",
        source="browser",
        target="svc-A",
        latency=_latency(),
    )
    graph = TopologyGraph(nodes=nodes, edges=[edge])
    assert graph.nodes.load_balancer is None



def test_edge_refers_unknown_node() -> None:
    """Edge pointing to a non-existent node fails validation."""
    nodes = _single_node_topology()
    bad_edge = Edge(
        id="edge-ghost",
        source="browser",
        target="ghost-srv",
        latency=_latency(),
    )
    with pytest.raises(ValidationError):
        TopologyGraph(nodes=nodes, edges=[bad_edge])


# --------------------------------------------------------------------------- #
# 2) LB is valid                                                                #
# --------------------------------------------------------------------------- #
def test_load_balancer_valid_graph() -> None:
    """LB covering a server with proper edges passes validation."""
    graph = _topology_with_lb({"svc-A"})
    assert graph.nodes.load_balancer is not None
    assert graph.nodes.load_balancer.server_covered == {"svc-A"}


# --------------------------------------------------------------------------- #
# 3) LB con server inesistente                                                #
# --------------------------------------------------------------------------- #
def test_lb_references_unknown_server() -> None:
    """LB that lists a non-existent server triggers ValidationError."""
    with pytest.raises(ValidationError):
        _topology_with_lb({"ghost-srv"})


# --------------------------------------------------------------------------- #
# 4) LB no edge with a server covered                                         #
# --------------------------------------------------------------------------- #
def test_lb_missing_edge_to_covered_server() -> None:
    """LB covers svc-A but edge LB→svc-A is missing → ValidationError."""
    # costruiamo il grafo senza l'edge lb-srv
    nodes = _single_node_topology()
    lb = LoadBalancer(id="lb-1", server_covered={"svc-A"})
    nodes = TopologyNodes(
        servers=nodes.servers,
        client=nodes.client,
        load_balancer=lb,
    )
    edges = [
        Edge(
            id="cli-lb",
            source="browser",
            target="lb-1",
            latency=_latency(),
        ),
    ]
    with pytest.raises(ValidationError):
        TopologyGraph(nodes=nodes, edges=edges)


