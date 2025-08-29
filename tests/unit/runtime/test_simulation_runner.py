"""Unit-tests for :pyclass:`app.runtime.simulation_runner.SimulationRunner`.

Purpose
-------
Validate each private builder in isolation and run a minimal end-to-end
execution without relying on the full integration scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import simpy
import yaml

from asyncflow.config.constants import Distribution, EventDescription
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    Server,
    ServerResources,
    TopologyNodes,
)

if TYPE_CHECKING:
    from pathlib import Path

    from asyncflow.runtime.actors.client import ClientRuntime
    from asyncflow.runtime.actors.rqs_generator import RqsGeneratorRuntime
    from asyncflow.schemas.settings.simulation import SimulationSettings
    from asyncflow.schemas.workload.rqs_generator import RqsGenerator



# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def env() -> simpy.Environment:
    """Return a fresh SimPy environment for every unit test."""
    return simpy.Environment()


@pytest.fixture
def runner(
    env: simpy.Environment,
    payload_base: SimulationPayload,
) -> SimulationRunner:
    """Factory producing an **un-started** SimulationRunner."""
    return SimulationRunner(env=env, simulation_input=payload_base)


# --------------------------------------------------------------------------- #
# Builder-level tests (original)                                              #
# --------------------------------------------------------------------------- #
def test_build_rqs_generator_populates_dict(runner: SimulationRunner) -> None:
    """_build_rqs_generator() must register one generator runtime."""
    runner._build_rqs_generator()  # noqa: SLF001
    assert len(runner._rqs_runtime) == 1  # noqa: SLF001
    gen_rt: RqsGeneratorRuntime = next(
        iter(runner._rqs_runtime.values()),  # noqa: SLF001
    )
    assert gen_rt.rqs_generator_data.id == runner.rqs_generator.id


def test_build_client_populates_dict(runner: SimulationRunner) -> None:
    """_build_client() must register exactly one client runtime."""
    runner._build_client()  # noqa: SLF001
    assert len(runner._client_runtime) == 1  # noqa: SLF001
    cli_rt: ClientRuntime = next(
        iter(runner._client_runtime.values()),  # noqa: SLF001
    )
    assert cli_rt.client_config.id == runner.client.id
    assert cli_rt.out_edge is None


def test_build_servers_keeps_empty_with_minimal_topology(
    runner: SimulationRunner,
) -> None:
    """Zero servers in the payload → dict stays empty."""
    runner._build_servers()  # noqa: SLF001
    assert runner._servers_runtime == {}  # noqa: SLF001


def test_build_load_balancer_noop_when_absent(
    runner: SimulationRunner,
) -> None:
    """No LB in the payload → builder leaves runtime as None."""
    runner._build_load_balancer()  # noqa: SLF001
    assert runner._lb_runtime is None  # noqa: SLF001


# --------------------------------------------------------------------------- #
# Edges builder (original)                                                    #
# --------------------------------------------------------------------------- #
def test_build_edges_with_stub_edge(runner: SimulationRunner) -> None:
    """
    `_build_edges()` must register exactly one `EdgeRuntime`, corresponding
    to the single stub edge (generator → client) present in the minimal
    topology fixture.
    """
    runner._build_rqs_generator()  # noqa: SLF001
    runner._build_client()  # noqa: SLF001
    runner._build_edges()  # noqa: SLF001
    assert len(runner._edges_runtime) == 1  # noqa: SLF001


# --------------------------------------------------------------------------- #
# from_yaml utility (original)                                                #
# --------------------------------------------------------------------------- #
def test_from_yaml_minimal(tmp_path: Path, env: simpy.Environment) -> None:
    """from_yaml() parses YAML, validates via Pydantic and returns a runner."""
    yml_payload = {
        "rqs_input": {
            "id": "gen-yaml",
            "avg_active_users": {"mean": 1},
            "avg_request_per_minute_per_user": {"mean": 2},
            "user_sampling_window": 10,
        },
        "topology_graph": {
            "nodes": {"client": {"id": "cli-yaml"}, "servers": []},
            "edges": [],
        },
        "sim_settings": {"total_simulation_time": 5},
    }

    yml_path: Path = tmp_path / "scenario.yml"
    yml_path.write_text(yaml.safe_dump(yml_payload))

    runner = SimulationRunner.from_yaml(env=env, yaml_path=yml_path)

    assert isinstance(runner, SimulationRunner)
    assert runner.rqs_generator.id == "gen-yaml"
    assert runner.client.id == "cli-yaml"


def _payload_with_lb_one_server_and_edges(
    *,
    rqs_input: RqsGenerator,
    sim_settings: SimulationSettings,
) -> SimulationPayload:
    """Build a small payload with LB → server wiring and one net edge."""
    client = Client(id="client-1")
    server = Server(id="srv-1", server_resources=ServerResources(), endpoints=[])
    lb = LoadBalancer(id="lb-1")
    nodes = TopologyNodes(servers=[server], client=client, load_balancer=lb)

    e_gen_lb = Edge(
        id="gen-lb",
        source=rqs_input.id,
        target=lb.id,
        latency=RVConfig(mean=0.001, distribution=Distribution.POISSON),
    )
    e_lb_srv = Edge(
        id="lb-srv",
        source=lb.id,
        target=server.id,
        latency=RVConfig(mean=0.002, distribution=Distribution.POISSON),
    )
    e_net = Edge(
        id="net-edge",
        source=rqs_input.id,
        target=client.id,
        latency=RVConfig(mean=0.003, distribution=Distribution.POISSON),
    )
    graph = TopologyGraph(nodes=nodes, edges=[e_gen_lb, e_lb_srv, e_net])

    return SimulationPayload(
        rqs_input=rqs_input,
        topology_graph=graph,
        sim_settings=sim_settings,
    )


def test_make_inbox_bound_to_env_and_fifo(runner: SimulationRunner) -> None:
    """_make_inbox() binds to runner.env and behaves FIFO."""
    box = runner._make_inbox()  # noqa: SLF001
    assert isinstance(box, simpy.Store)

    # Put two items and consume them in order using `run(until=...)`.
    env = runner.env
    env.run(until=box.put("first"))
    env.run(until=box.put("second"))
    got1 = env.run(until=box.get())
    got2 = env.run(until=box.get())
    assert got1 == "first"
    assert got2 == "second"


def test_build_load_balancer_when_present(
    env: simpy.Environment,
    rqs_input: RqsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """_build_load_balancer() should create `_lb_runtime` if LB exists."""
    payload = _payload_with_lb_one_server_and_edges(
        rqs_input=rqs_input, sim_settings=sim_settings,
    )
    sr = SimulationRunner(env=env, simulation_input=payload)

    sr._build_load_balancer()  # noqa: SLF001
    assert sr._lb_runtime is not None  # noqa: SLF001
    assert sr._lb_runtime.lb_config.id == "lb-1"  # noqa: SLF001


def test_build_edges_populates_lb_out_edges_and_sources(
    env: simpy.Environment,
    rqs_input: RqsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """_build_edges() wires generator→LB and populates `_lb_out_edges`."""
    payload = _payload_with_lb_one_server_and_edges(
        rqs_input=rqs_input, sim_settings=sim_settings,
    )
    sr = SimulationRunner(env=env, simulation_input=payload)

    sr._build_rqs_generator()  # noqa: SLF001
    sr._build_client()  # noqa: SLF001
    sr._build_servers()  # noqa: SLF001
    sr._build_load_balancer()  # noqa: SLF001
    sr._build_edges()  # noqa: SLF001

    assert "lb-srv" in sr._lb_out_edges  # noqa: SLF001
    assert len(sr._edges_runtime) >= 2  # noqa: SLF001
    gen_rt = next(iter(sr._rqs_runtime.values()))  # noqa: SLF001
    assert gen_rt.out_edge is not None


def test_build_events_attaches_shared_views(
    env: simpy.Environment,
    rqs_input: RqsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """_build_events() attaches shared `edges_affected` and `edges_spike` views."""
    payload = _payload_with_lb_one_server_and_edges(
        rqs_input=rqs_input, sim_settings=sim_settings,
    )
    spike = EventInjection(
        event_id="ev-spike",
        target_id="net-edge",
        start={
            "kind": EventDescription.NETWORK_SPIKE_START,
            "t_start": 0.2,
            "spike_s": 0.05,
        },
        end={"kind": EventDescription.NETWORK_SPIKE_END, "t_end": 0.4},
    )
    outage = EventInjection(
        event_id="ev-out",
        target_id="srv-1",
        start={"kind": EventDescription.SERVER_DOWN, "t_start": 0.1},
        end={"kind": EventDescription.SERVER_UP, "t_end": 0.3},
    )
    payload.events = [spike, outage]

    sr = SimulationRunner(env=env, simulation_input=payload)
    sr._build_rqs_generator()  # noqa: SLF001
    sr._build_client()  # noqa: SLF001
    sr._build_servers()  # noqa: SLF001
    sr._build_load_balancer()  # noqa: SLF001
    sr._build_edges()  # noqa: SLF001
    sr._build_events()  # noqa: SLF001

    assert sr._events_runtime is not None  # noqa: SLF001
    events_rt = sr._events_runtime # noqa: SLF001

    assert "net-edge" in events_rt.edges_affected
    for er in sr._edges_runtime.values():  # noqa: SLF001
        assert er.edges_spike is not None
        assert er.edges_affected is events_rt.edges_affected


