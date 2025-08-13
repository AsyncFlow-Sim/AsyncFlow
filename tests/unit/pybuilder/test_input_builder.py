"""
Unit tests for the AsyncFlow builder.

The goal is to verify that:
- The builder enforces types on each `add_*` method.
- Missing components produce clear ValueError exceptions on `build_payload()`.
- A valid, minimal scenario builds a `SimulationPayload` successfully.
- Methods return `self` to support fluent chaining.
- Servers and edges can be added in multiples and preserve order.
"""

from __future__ import annotations

import pytest

from asyncflow.pybuilder.input_builder import AsyncFlow
from asyncflow.schemas.full_simulation_input import SimulationPayload
from asyncflow.schemas.rqs_generator_input import RqsGeneratorInput
from asyncflow.schemas.simulation_settings_input import SimulationSettings
from asyncflow.schemas.system_topology.endpoint import Endpoint
from asyncflow.schemas.system_topology.full_system_topology import Client, Edge, Server


# --------------------------------------------------------------------------- #
# Helpers: build minimal, valid components                                    #
# --------------------------------------------------------------------------- #
def make_generator() -> RqsGeneratorInput:
    """Return a minimal valid request generator."""
    return RqsGeneratorInput(
        id="rqs-1",
        avg_active_users={"mean": 10},
        avg_request_per_minute_per_user={"mean": 30},
        user_sampling_window=60,
    )


def make_client() -> Client:
    """Return a minimal valid client."""
    return Client(id="client-1")


def make_endpoint() -> Endpoint:
    """Return a minimal endpoint with CPU and IO steps."""
    return Endpoint(
        endpoint_name="ep-1",
        probability=1.0,
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.001}},
        ],
    )


def make_server(server_id: str = "srv-1") -> Server:
    """Return a minimal valid server with 1 core, 2GB RAM, and one endpoint."""
    return Server(
        id=server_id,
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[make_endpoint()],
    )


def make_edges() -> list[Edge]:
    """Return a valid edge triplet for the minimal single-server scenario."""
    e1 = Edge(
        id="gen-to-client",
        source="rqs-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e2 = Edge(
        id="client-to-server",
        source="client-1",
        target="srv-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e3 = Edge(
        id="server-to-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    return [e1, e2, e3]


def make_settings() -> SimulationSettings:
    """Return minimal simulation settings within validation bounds."""
    return SimulationSettings(
        total_simulation_time=5.0,  # lower bound is 5 seconds
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
# Positive / “happy path”                                                     #
# --------------------------------------------------------------------------- #
def test_builder_happy_path_returns_payload() -> None:
    """Building a minimal scenario returns a validated SimulationPayload."""
    flow = AsyncFlow()
    generator = make_generator()
    client = make_client()
    server = make_server()
    e1, e2, e3 = make_edges()
    settings = make_settings()

    payload = (
        flow.add_generator(generator)
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
    """Every add_* method returns `self` to support fluent chaining."""
    flow = AsyncFlow()
    ret = (
        flow.add_generator(make_generator())
        .add_client(make_client())
        .add_servers(make_server())
        .add_edges(*make_edges())
        .add_simulation_settings(make_settings())
    )
    assert ret is flow


def test_add_servers_accepts_multiple_and_keeps_order() -> None:
    """Adding multiple servers keeps insertion order."""
    flow = AsyncFlow().add_generator(make_generator()).add_client(make_client())
    s1 = make_server("srv-1")
    s2 = make_server("srv-2")
    s3 = make_server("srv-3")

    flow.add_servers(s1, s2).add_servers(s3)
    e1, e2, e3 = make_edges()
    settings = make_settings()
    payload = (
        flow.add_edges(e1, e2, e3)
        .add_simulation_settings(settings)
        .build_payload()
    )

    ids = [srv.id for srv in payload.topology_graph.nodes.servers]
    assert ids == ["srv-1", "srv-2", "srv-3"]


# --------------------------------------------------------------------------- #
# Negative cases: missing components                                          #
# --------------------------------------------------------------------------- #
def test_build_without_generator_raises() -> None:
    """Building without a generator fails with a clear error."""
    flow = AsyncFlow()
    flow.add_client(make_client())
    flow.add_servers(make_server())
    flow.add_edges(*make_edges())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="The generator input must be instantiated before the simulation",
    ):
        flow.build_payload()


def test_build_without_client_raises() -> None:
    """Building without a client fails with a clear error."""
    flow = AsyncFlow()
    flow.add_generator(make_generator())
    flow.add_servers(make_server())
    flow.add_edges(*make_edges())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="The client input must be instantiated before the simulation",
    ):
        flow.build_payload()


def test_build_without_servers_raises() -> None:
    """Building without servers fails with a clear error."""
    flow = AsyncFlow()
    flow.add_generator(make_generator())
    flow.add_client(make_client())
    flow.add_edges(*make_edges())
    flow.add_simulation_settings(make_settings())

    with pytest.raises(
        ValueError,
        match="You must instantiate at least one server before the simulation",
    ):
        flow.build_payload()


def test_build_without_edges_raises() -> None:
    """Building without edges fails with a clear error."""
    flow = AsyncFlow()
    flow.add_generator(make_generator())
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
    flow.add_generator(make_generator())
    flow.add_client(make_client())
    flow.add_servers(make_server())
    flow.add_edges(*make_edges())

    with pytest.raises(
        ValueError,
        match="The simulation settings must be instantiated before the simulation",
    ):
        flow.build_payload()


# --------------------------------------------------------------------------- #
# Negative cases: type enforcement in add_* methods                           #
# --------------------------------------------------------------------------- #
def test_add_generator_rejects_wrong_type() -> None:
    """`add_generator` rejects non-RqsGeneratorInput instances."""
    flow = AsyncFlow()
    with pytest.raises(TypeError):
        flow.add_generator("not-a-generator") # type: ignore[arg-type]


def test_add_client_rejects_wrong_type() -> None:
    """`add_client` rejects non-Client instances."""
    flow = AsyncFlow()
    with pytest.raises(TypeError):
        flow.add_client(1234) # type: ignore[arg-type]


def test_add_servers_rejects_wrong_type() -> None:
    """`add_servers` rejects any non-Server in the varargs."""
    flow = AsyncFlow()
    good = make_server()
    with pytest.raises(TypeError):
        flow.add_servers(good, "not-a-server") # type: ignore[arg-type]


def test_add_edges_rejects_wrong_type() -> None:
    """`add_edges` rejects any non-Edge in the varargs."""
    flow = AsyncFlow()
    good = make_edges()[0]
    with pytest.raises(TypeError):
        flow.add_edges(good, 3.14) # type: ignore[arg-type]


def test_add_settings_rejects_wrong_type() -> None:
    """`add_simulation_settings` rejects non-SimulationSettings instances."""
    flow = AsyncFlow()
    with pytest.raises(TypeError):
        flow.add_simulation_settings({"total_simulation_time": 1.0}) # type: ignore[arg-type]
