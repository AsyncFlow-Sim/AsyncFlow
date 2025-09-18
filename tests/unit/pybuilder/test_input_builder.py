"""
Unit tests for the AsyncFlow builder.

Goals:
- Enforce types on each `add_*` method.
- Missing parts raise clear ValueErrors on `build_payload()`.
- Minimal valid scenario builds a SimulationPayload.
- Methods return `self` to support fluent chaining.
- Servers and edges can be added in multiples and preserve order.
- New features: LinkEdge-only topologies and homogeneous edge enforcement.
"""

from __future__ import annotations

import pytest

from asyncflow.builder.asyncflow_builder import AsyncFlow
from asyncflow.config.enums import EventDescription, SystemEdges
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import LinkEdge, NetworkEdge
from asyncflow.schemas.topology.endpoint import Endpoint
from asyncflow.schemas.topology.nodes import Client, Server

# --------------------------------------------------------------------------- #
# Helpers: minimal, valid components                                          #
# --------------------------------------------------------------------------- #


def make_generator() -> ArrivalsGenerator:
    """Minimal valid request generator."""
    return ArrivalsGenerator(id="rqs-1", lambda_rps=10, model="poisson")


def make_client() -> Client:
    """Minimal valid client."""
    return Client(id="client-1")


def make_endpoint() -> Endpoint:
    """Endpoint with CPU and IO steps."""
    return Endpoint(
        endpoint_name="ep-1",
        probability=1.0,
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.001}},
        ],
    )


def make_server(server_id: str = "srv-1") -> Server:
    """Server with 1 core, 2GB RAM, and one endpoint."""
    return Server(
        id=server_id,
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[make_endpoint()],
    )


def make_net_edges() -> list[NetworkEdge]:
    """Network edges for a single-server scenario."""
    e1 = NetworkEdge(
        id="gen-to-client",
        source="rqs-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e2 = NetworkEdge(
        id="client-to-server",
        source="client-1",
        target="srv-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e3 = NetworkEdge(
        id="server-to-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    return [e1, e2, e3]


def make_link_edges() -> list[LinkEdge]:
    """Link-only edges for a single-server scenario."""
    e1 = LinkEdge(id="gen-to-client", source="rqs-1", target="client-1")
    e2 = LinkEdge(id="client-to-server", source="client-1", target="srv-1")
    e3 = LinkEdge(id="server-to-client", source="srv-1", target="client-1")
    return [e1, e2, e3]


def make_settings() -> SimulationSettings:
    """Minimal simulation settings within validation bounds."""
    return SimulationSettings(
        total_simulation_time=5.0,
        sample_period_s=0.1,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )


# --------------------------------------------------------------------------- #
# Positive / happy path                                                       #
# --------------------------------------------------------------------------- #


def test_builder_happy_path_returns_payload() -> None:
    """Minimal scenario builds a validated SimulationPayload."""
    flow = AsyncFlow()
    generator = make_generator()
    client = make_client()
    server = make_server()
    e1, e2, e3 = make_net_edges()
    settings = make_settings()

    payload = (
        flow.add_arrivals_generator(generator)
        .add_client(client)
        .add_servers(server)
        .add_edges(e1, e2, e3)
        .add_simulation_settings(settings)
        .build_payload()
    )

    assert isinstance(payload, SimulationPayload)
    assert payload.topology_graph.nodes.client.id == client.id
    assert len(payload.topology_graph.nodes.servers) == 1
    assert {e.id for e in payload.topology_graph.edges} == {
        "gen-to-client",
        "client-to-server",
        "server-to-client",
    }


def test_add_methods_return_self_for_chaining() -> None:
    """Every add_* method returns `self` for fluent chaining."""
    flow = AsyncFlow()
    ret = (
        flow.add_arrivals_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
        .add_edges(*make_net_edges())
        .add_simulation_settings(make_settings())
    )
    assert ret is flow


def test_add_servers_accepts_multiple_and_keeps_order() -> None:
    """Adding multiple servers keeps insertion order."""
    flow = AsyncFlow()
    flow.add_arrivals_generator(make_generator()).add_client(make_client())
    s1 = make_server("srv-1")
    s2 = make_server("srv-2")
    s3 = make_server("srv-3")

    flow.add_servers(s1, s2).add_servers(s3)
    e1, e2, e3 = make_net_edges()
    settings = make_settings()
    payload = (
        flow.add_edges(e1, e2, e3).add_simulation_settings(settings).build_payload()
    )

    ids = [srv.id for srv in payload.topology_graph.nodes.servers]
    assert ids == ["srv-1", "srv-2", "srv-3"]


# --------------------------------------------------------------------------- #
# Negative: missing components                                                #
# --------------------------------------------------------------------------- #


def test_build_without_generator_raises() -> None:
    """Building without a generator fails with a clear error."""
    flow = AsyncFlow()
    flow.add_client(make_client())
    flow.add_servers(make_server())
    flow.add_edges(*make_net_edges())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="The arrivals generator must be instantiated before the simulation",
    ):
        flow.build_payload()


def test_build_without_client_raises() -> None:
    """Building without a client fails with a clear error."""
    flow = AsyncFlow()
    flow.add_arrivals_generator(make_generator())
    flow.add_servers(make_server())
    flow.add_edges(*make_net_edges())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="The client input must be instantiated before the simulation",
    ):
        flow.build_payload()


def test_build_without_servers_raises() -> None:
    """Building without servers fails with a clear error."""
    flow = AsyncFlow()
    flow.add_arrivals_generator(make_generator())
    flow.add_client(make_client())
    flow.add_edges(*make_net_edges())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="You must instantiate at least one server before the simulation",
    ):
        flow.build_payload()


def test_build_without_edges_raises() -> None:
    """Building without edges fails with a clear error."""
    flow = AsyncFlow()
    flow.add_arrivals_generator(make_generator())
    flow.add_client(make_client())
    flow.add_servers(make_server())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="You must instantiate edges before the simulation",
    ):
        flow.build_payload()


def test_build_without_settings_raises() -> None:
    """Building without settings fails with a clear error."""
    flow = AsyncFlow()
    flow.add_arrivals_generator(make_generator())
    flow.add_client(make_client())
    flow.add_servers(make_server())
    flow.add_edges(*make_net_edges())

    with pytest.raises(
        ValueError,
        match="The simulation settings must be instantiated before the simulation",
    ):
        flow.build_payload()


# --------------------------------------------------------------------------- #
# Negative: type enforcement in add_* methods                                 #
# --------------------------------------------------------------------------- #


def test_add_generator_rejects_wrong_type() -> None:
    """`add_arrivals_generator` rejects non-ArrivalsGenerator instances."""
    flow = AsyncFlow()
    with pytest.raises(TypeError):
        flow.add_arrivals_generator("not-a-generator")  # type: ignore[arg-type]


def test_add_client_rejects_wrong_type() -> None:
    """`add_client` rejects non-Client instances."""
    flow = AsyncFlow()
    with pytest.raises(TypeError):
        flow.add_client(1234)  # type: ignore[arg-type]


def test_add_servers_rejects_wrong_type() -> None:
    """`add_servers` rejects any non-Server in the varargs."""
    flow = AsyncFlow()
    good = make_server()
    with pytest.raises(TypeError):
        flow.add_servers(good, "not-a-server")  # type: ignore[arg-type]


def test_add_edges_rejects_wrong_type() -> None:
    """`add_edges` rejects any non-Edge in the varargs."""
    flow = AsyncFlow()
    good = make_net_edges()[0]
    with pytest.raises(TypeError):
        flow.add_edges(good, 3.14)  # type: ignore[arg-type]


def test_add_settings_rejects_wrong_type() -> None:
    """`add_simulation_settings` rejects non-SimulationSettings instances."""
    flow = AsyncFlow()
    with pytest.raises(TypeError):
        flow.add_simulation_settings({"total_simulation_time": 1.0})  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# New features: LinkEdge support and homogeneous enforcement                   #
# --------------------------------------------------------------------------- #


def test_linkedge_topology_builds_payload() -> None:
    """A LinkEdge-only topology is accepted and preserved."""
    flow = AsyncFlow()
    payload = (
        flow.add_arrivals_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
        .add_edges(*make_link_edges())
        .add_simulation_settings(make_settings())
        .build_payload()
    )
    assert all(
        e.edge_type is SystemEdges.LINK_CONNECTION
        for e in payload.topology_graph.edges
    )
    assert {e.id for e in payload.topology_graph.edges} == {
        "gen-to-client",
        "client-to-server",
        "server-to-client",
    }


def test_add_edges_rejects_mixed_types_in_single_call() -> None:
    """Mixing NetworkEdge and LinkEdge in the same call is rejected."""
    flow = (
        AsyncFlow()
        .add_arrivals_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
    )
    n1 = make_net_edges()[0]
    l1 = make_link_edges()[0]
    with pytest.raises(TypeError, match="Cannot mix (LinkEdge|NetworkEdge)"):
        flow.add_edges(n1, l1)


def test_add_edges_rejects_mixed_types_across_calls() -> None:
    """Once kind is fixed, subsequent calls with other kind fail."""
    flow = (
        AsyncFlow()
        .add_arrivals_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
    )
    n1, _, _ = make_net_edges()
    flow.add_edges(n1)
    with pytest.raises(TypeError, match="Cannot mix LinkEdge with NetworkEdge."):
        flow.add_edges(make_link_edges()[0])

    flow2 = (
        AsyncFlow()
        .add_arrivals_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
    )
    l1, _, _ = make_link_edges()
    flow2.add_edges(l1)
    with pytest.raises(TypeError, match="Cannot mix NetworkEdge with LinkEdge."):
        flow2.add_edges(make_net_edges()[0])


def test_add_edges_noop_on_empty_call() -> None:
    """Calling add_edges() with no args is a no-op and does not fix kind."""
    flow = AsyncFlow()
    flow.add_arrivals_generator(make_generator())
    flow.add_client(make_client())
    flow.add_servers(make_server())
    flow.add_simulation_settings(make_settings())

    ret = flow.add_edges()  # no edges
    assert ret is flow

    with pytest.raises(ValueError, match="You must instantiate edges"):
        flow.build_payload()


# --------------------------------------------------------------------------- #
# Events helpers                                                               #
# --------------------------------------------------------------------------- #


def test_add_network_spike_is_in_payload() -> None:
    """add_network_spike wires a NETWORK_SPIKE event into the payload."""
    n1, n2, n3 = make_net_edges()
    flow = (
        AsyncFlow()
        .add_arrivals_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
        .add_edges(n1, n2, n3)
        .add_network_spike(
            event_id="ev1",
            edge_id=n2.id,
            t_start=1.0,
            t_end=2.0,
            spike_s=0.25,
        )
        .add_simulation_settings(make_settings())
    )
    payload = flow.build_payload()
    assert payload.events is not None
    assert len(payload.events) == 1
    ev = payload.events[0]
    assert isinstance(ev, EventInjection)
    assert ev.event_id == "ev1"
    assert ev.target_id == n2.id
    assert ev.start.kind is EventDescription.NETWORK_SPIKE_START
    assert ev.end.kind is EventDescription.NETWORK_SPIKE_END
    assert ev.start.spike_s == 0.25
