"""Unit-tests for :class:`SimulationRunner`.

Purpose
-------
Validate each private builder in isolation and run a minimal end-to-end
execution without relying on the full integration scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
import simpy
import yaml
from tests.unit.helpers import make_min_ep

from asyncflow.config.enums import Distribution, EventDescription
from asyncflow.runner.simulation import SimulationRunner
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import LinkEdge, NetworkEdge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    NodesResources,
    Server,
    TopologyNodes,
)

if TYPE_CHECKING:
    from pathlib import Path

    from asyncflow.runtime.actors.arrivals_generator import (
        ArrivalsGeneratorRuntime,
    )
    from asyncflow.runtime.actors.client import ClientRuntime


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def env() -> simpy.Environment:
    """Return a fresh SimPy environment for every unit test."""
    return simpy.Environment()


@pytest.fixture
def payload_base() -> SimulationPayload:
    """Minimal SimulationPayload: arrivals + client, no servers."""
    arrivals = ArrivalsGenerator(
        id="gen",
        lambda_rps=5.0,
        model=Distribution.POISSON,
    )
    client = Client(id="cli")
    nodes = TopologyNodes(servers=[], client=client, load_balancer=None)
    graph = TopologyGraph(nodes=nodes, edges=[])
    settings = SimulationSettings(total_simulation_time=5)
    return SimulationPayload(
        arrivals=arrivals,
        topology_graph=graph,
        sim_settings=settings,
    )


@pytest.fixture
def runner(
    env: simpy.Environment,
    payload_base: SimulationPayload,
) -> SimulationRunner:
    """Factory producing an **un-started** SimulationRunner."""
    return SimulationRunner(env=env, simulation_input=payload_base)


# --------------------------------------------------------------------------- #
# Builder-level tests                                                         #
# --------------------------------------------------------------------------- #
def test_build_arrivals_populates_dict(runner: SimulationRunner) -> None:
    """_build_rqs_generator() must register one generator runtime."""
    runner._build_rqs_generator()  # noqa: SLF001
    assert len(runner._arrivals_runtime) == 1  # noqa: SLF001
    gen_rt: ArrivalsGeneratorRuntime = next(
        iter(runner._arrivals_runtime.values()), # noqa: SLF001
    )
    assert gen_rt.arrivals.id == runner.arrivals.id


def test_build_client_populates_dict(runner: SimulationRunner) -> None:
    """_build_client() must register exactly one client runtime."""
    runner._build_client()  # noqa: SLF001
    assert len(runner._client_runtime) == 1  # noqa: SLF001
    cli_rt: ClientRuntime = next(
        iter(runner._client_runtime.values()), # noqa: SLF001
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
# Edges builder                                                               #
# --------------------------------------------------------------------------- #
def test_build_edges_with_stub_network_edge(runner: SimulationRunner) -> None:
    """Register exactly one EdgeRuntime for a NetworkEdge (gen → cli)."""
    arrivals_id = runner.arrivals.id
    client_id = runner.client.id
    stub_edge = NetworkEdge(
        id="gen-cli",
        source=arrivals_id,
        target=client_id,
        latency=RVConfig(mean=0.001, distribution=Distribution.POISSON),
    )

    # Tipizza esplicitamente la lista come list[NetworkEdge]
    net_edges: list[NetworkEdge] = [stub_edge]
    runner.edges = cast("list[NetworkEdge] | list[LinkEdge]", net_edges)

    runner._build_rqs_generator()  # noqa: SLF001
    runner._build_client()         # noqa: SLF001
    runner._build_edges()          # noqa: SLF001

    assert len(runner._edges_runtime) == 1  # noqa: SLF001

def test_build_edges_with_stub_link_edge(runner: SimulationRunner) -> None:
    """Register exactly one EdgeRuntime for a LinkEdge (gen → cli)."""
    arrivals_id = runner.arrivals.id
    client_id = runner.client.id
    stub_edge = LinkEdge(id="gen-cli", source=arrivals_id, target=client_id)

    # Tipizza esplicitamente la lista come list[LinkEdge]
    link_edges: list[LinkEdge] = [stub_edge]
    runner.edges = cast("list[NetworkEdge] | list[LinkEdge]", link_edges)

    runner._build_rqs_generator()  # noqa: SLF001
    runner._build_client()         # noqa: SLF001
    runner._build_edges()          # noqa: SLF001

    assert len(runner._edges_runtime) == 1  # noqa: SLF001

# --------------------------------------------------------------------------- #
# from_yaml utility                                                           #
# --------------------------------------------------------------------------- #
def test_from_yaml_minimal(tmp_path: Path, env: simpy.Environment) -> None:
    """from_yaml() parses YAML, validates and returns a runner."""
    yml_payload = {
        "arrivals": {"id": "gen-yaml", "lambda_rps": 3.0, "model": "poisson"},
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
    assert runner.arrivals.id == "gen-yaml"
    assert runner.client.id == "cli-yaml"


# --------------------------------------------------------------------------- #
# Helpers for richer payloads                                                 #
# --------------------------------------------------------------------------- #
def _payload_with_lb_one_server_and_edges(
    *,
    arrivals: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> SimulationPayload:
    """Build a small payload with LB → server wiring and one net edge."""
    client = Client(id="client-1")
    server = Server(
        id="srv-1",
        server_resources=NodesResources(),
        endpoints=[make_min_ep()],
    )
    lb = LoadBalancer(id="lb-1")
    nodes = TopologyNodes(servers=[server], client=client, load_balancer=lb)

    e_gen_lb = NetworkEdge(
        id="gen-lb",
        source=arrivals.id,
        target=lb.id,
        latency=RVConfig(mean=0.001, distribution=Distribution.POISSON),
    )
    e_lb_srv = NetworkEdge(
        id="lb-srv",
        source=lb.id,
        target=server.id,
        latency=RVConfig(mean=0.002, distribution=Distribution.POISSON),
    )
    e_net = NetworkEdge(
        id="net-edge",
        source=arrivals.id,
        target=client.id,
        latency=RVConfig(mean=0.003, distribution=Distribution.POISSON),
    )
    graph = TopologyGraph(nodes=nodes, edges=[e_gen_lb, e_lb_srv, e_net])

    return SimulationPayload(
        arrivals=arrivals,
        topology_graph=graph,
        sim_settings=sim_settings,
    )


# --------------------------------------------------------------------------- #
# Additional builder tests                                                    #
# --------------------------------------------------------------------------- #
def test_make_inbox_bound_to_env_and_fifo(runner: SimulationRunner) -> None:
    """_make_inbox() binds to runner.env and behaves FIFO."""
    box = runner._make_inbox()  # noqa: SLF001
    assert isinstance(box, simpy.Store)

    env = runner.env
    env.run(until=box.put("first"))
    env.run(until=box.put("second"))
    got1 = env.run(until=box.get())
    got2 = env.run(until=box.get())
    assert (got1, got2) == ("first", "second")


def test_build_load_balancer_when_present(env: simpy.Environment) -> None:
    """_build_load_balancer() should create `_lb_runtime` if LB exists."""
    arrivals = ArrivalsGenerator(
        id="gen",
        lambda_rps=5.0,
        model=Distribution.POISSON,
    )
    settings = SimulationSettings(total_simulation_time=5)
    payload = _payload_with_lb_one_server_and_edges(
        arrivals=arrivals,
        sim_settings=settings,
    )

    sr = SimulationRunner(env=env, simulation_input=payload)
    sr._build_load_balancer()  # noqa: SLF001

    assert sr._lb_runtime is not None  # noqa: SLF001
    assert sr._lb_runtime.lb_config.id == "lb-1"  # noqa: SLF001


def test_build_edges_populates_lb_out_edges_and_sources(
    env: simpy.Environment,
) -> None:
    """_build_edges() wires generator→LB and populates `_lb_out_edges`."""
    arrivals = ArrivalsGenerator(
        id="gen",
        lambda_rps=5.0,
        model=Distribution.POISSON,
    )
    settings = SimulationSettings(total_simulation_time=5)
    payload = _payload_with_lb_one_server_and_edges(
        arrivals=arrivals,
        sim_settings=settings,
    )

    sr = SimulationRunner(env=env, simulation_input=payload)
    sr._build_rqs_generator()  # noqa: SLF001
    sr._build_client()  # noqa: SLF001
    sr._build_servers()  # noqa: SLF001
    sr._build_load_balancer()  # noqa: SLF001
    sr._build_edges()  # noqa: SLF001

    assert "lb-srv" in sr._lb_out_edges  # noqa: SLF001
    assert len(sr._edges_runtime) >= 2  # noqa: SLF001
    gen_rt = next(iter(sr._arrivals_runtime.values()))  # noqa: SLF001
    assert gen_rt.out_edge is not None


def test_build_events_attaches_shared_views(env: simpy.Environment) -> None:
    """_build_events() attaches shared `edges_affected` & `edges_spike`."""
    arrivals = ArrivalsGenerator(
        id="gen",
        lambda_rps=5.0,
        model=Distribution.POISSON,
    )
    settings = SimulationSettings(total_simulation_time=5)
    payload = _payload_with_lb_one_server_and_edges(
        arrivals=arrivals,
        sim_settings=settings,
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
    events_rt = sr._events_runtime  # noqa: SLF001

    assert "net-edge" in events_rt.edges_affected
    for er in sr._edges_runtime.values():  # noqa: SLF001
        assert er.edges_spike is not None
        assert er.edges_affected is events_rt.edges_affected

