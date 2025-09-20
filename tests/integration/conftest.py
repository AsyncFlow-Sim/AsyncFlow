"""Project-wide fixtures and factory-fixtures for integration tests.

Design goals
------------
- DRY: shared builders live here (arrivals, servers, edges, topologies, events).
- Flexible: factory fixtures let tests customize times/means without repetition.
- Safe: each test gets a fresh SimPy env; no state leakage between tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pytest
import simpy

from asyncflow.config.enums import (
    Distribution,
    EndpointStepCPU,
    EventDescription,
    StepOperation,
)
from asyncflow.runner.simulation import SimulationRunner
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import NetworkEdge
from asyncflow.schemas.topology.endpoint import Endpoint, Step
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    NodesResources,
    Server,
    TopologyNodes,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# --------------------------------------------------------------------------- #
# Core environment / runner helpers                                           #
# --------------------------------------------------------------------------- #

@pytest.fixture
def env() -> simpy.Environment:
    """Fresh SimPy environment per test."""
    return simpy.Environment()


@pytest.fixture
def sim_settings() -> SimulationSettings:
    """Default short horizon; tests can override via model_copy()."""
    return SimulationSettings(total_simulation_time=5)


@pytest.fixture
def make_runner_from_yaml(
    env: simpy.Environment,
) -> Callable[[str | Path], SimulationRunner]:
    """Factory that loads a YAML scenario and returns a SimulationRunner."""

    def _factory(yaml_path: str | Path) -> SimulationRunner:
        return SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)

    return _factory


@pytest.fixture
def make_runner_from_payload(
    env: simpy.Environment,
) -> Callable[[SimulationPayload], SimulationRunner]:
    """Factory that wraps a validated payload into a SimulationRunner."""

    def _factory(payload: SimulationPayload) -> SimulationRunner:
        return SimulationRunner(env=env, simulation_input=payload)

    return _factory


# --------------------------------------------------------------------------- #
# Arrivals / servers / edges factories                                        #
# --------------------------------------------------------------------------- #

@pytest.fixture
def arrivals_factory() -> Callable[[str, float, Distribution], ArrivalsGenerator]:
    """Build an ArrivalsGenerator with the chosen rate and model."""

    def _make(
        rid: str,
        lambda_rps: float = 20.0,
        model: Distribution = Distribution.POISSON,
    ) -> ArrivalsGenerator:
        return ArrivalsGenerator(id=rid, lambda_rps=lambda_rps, model=model)

    return _make


@pytest.fixture
def arrivals_poisson(
    arrivals_factory: Callable[..., ArrivalsGenerator],
    ) -> ArrivalsGenerator:
    """Convenience: Poisson arrivals @ 20 rps."""
    return arrivals_factory("rqs-1", 20.0, Distribution.POISSON)


@pytest.fixture
def server_factory() -> Callable[[str, float | None], Server]:
    """
    Build a server. If `service_time_s` is None, the server has no steps.
    Otherwise, a single CPU step with mean service time is created.
    """

    def _make(sid: str, service_time_s: float | None = 0.001) -> Server:
        if service_time_s is None:
            endpoints: list[Endpoint] = []
        else:
            ep = Endpoint(
                endpoint_name="get",
                steps=[
                    Step(
                        kind=EndpointStepCPU.CPU_BOUND_OPERATION,
                        step_operation={StepOperation.CPU_TIME: service_time_s},
                    ),
                ],
            )
            endpoints = [ep]
        return Server(id=sid, server_resources=NodesResources(), endpoints=endpoints)

    return _make


class EdgeFactory(Protocol):
    """Callable that builds an `Edge` with a latency RV."""

    def __call__(
        self,
        eid: str,
        src: str,
        tgt: str,
        mean: float,
        dist: Distribution = ...,
    ) -> NetworkEdge:
        """Return an `Edge` from ids and latency parameters."""


@pytest.fixture
def edge_factory() -> Callable[..., NetworkEdge]:
    """
    Build an edge with a latency RV. Defaults to Poisson(mean=1ms) to keep
    tests fast; pass another distribution/mean when needed.
    """

    def _make(
        eid: str,
        src: str,
        tgt: str,
        mean: float = 0.001,
        dist: Distribution = Distribution.POISSON,
    ) -> NetworkEdge:
        return NetworkEdge(
            id=eid,
            source=src,
            target=tgt,
            latency=RVConfig(mean=mean, distribution=dist),
        )

    return _make


# --------------------------------------------------------------------------- #
# Topology builders                                                           #
# --------------------------------------------------------------------------- #

class TwoServersBuilder(Protocol):
    """Callable that returns a two-server `TopologyGraph`."""

    def __call__(
        self, *, service_time_s: float | None = ..., edge_mean: float = ...,
    ) -> TopologyGraph:
        """Build the graph with two servers and a load balancer."""


class SingleServerBuilder(Protocol):
    """Callable that returns a single-server `TopologyGraph`."""

    def __call__(
        self, *, service_time_s: float | None = ..., edge_mean: float = ...,
    ) -> TopologyGraph:
        """Build the graph with one server and a load balancer."""


@pytest.fixture
def topology_two_servers(
    server_factory: Callable[[str, float | None], Server],
    edge_factory: Callable[..., NetworkEdge],
) -> Callable[..., TopologyGraph]:
    """Factory for a two-server topology with a load balancer"""
    def _make(*, service_time_s: float | None = 0.001,
              edge_mean: float = 0.001) -> TopologyGraph:
        client = Client(id="client-1")
        lb = LoadBalancer(id="lb-1")
        srv1 = server_factory("srv-1", service_time_s)
        srv2 = server_factory("srv-2", service_time_s)

        edges = [
            edge_factory("gen-to-client", "rqs-1", "client-1", edge_mean),
            edge_factory("client-to-lb", "client-1", "lb-1", edge_mean),
            edge_factory("lb-to-srv1", "lb-1", "srv-1", edge_mean),
            edge_factory("lb-to-srv2", "lb-1", "srv-2", edge_mean),
            edge_factory("srv1-to-gen", "srv-1", "rqs-1", edge_mean),
            edge_factory("srv2-to-gen", "srv-2", "rqs-1", edge_mean),
        ]
        nodes = TopologyNodes(
            servers=[srv1, srv2], client=client, load_balancer=lb,
        )
        return TopologyGraph(nodes=nodes, edges=edges)
    return _make


@pytest.fixture
def topology_single_server(
    server_factory: Callable[[str, float | None], Server],
    edge_factory: Callable[..., NetworkEdge],
) -> Callable[..., TopologyGraph]:
    """Factory for a single-server topology with a load balancer in front"""
    def _make(*, service_time_s: float | None = 0.001,
              edge_mean: float = 0.001) -> TopologyGraph:
        client = Client(id="client-1")
        lb = LoadBalancer(id="lb-1")
        srv = server_factory("srv-1", service_time_s)

        edges = [
            edge_factory("gen-to-client", "rqs-1", "client-1", edge_mean),
            edge_factory("client-to-lb", "client-1", "lb-1", edge_mean),
            edge_factory("lb-to-srv1", "lb-1", "srv-1", edge_mean),
            edge_factory("srv1-to-gen", "srv-1", "rqs-1", edge_mean),
        ]
        nodes = TopologyNodes(
            servers=[srv], client=client, load_balancer=lb,
        )
        return TopologyGraph(nodes=nodes, edges=edges)
    return _make

# --------------------------------------------------------------------------- #
# Event factories                                                             #
# --------------------------------------------------------------------------- #

@pytest.fixture
def spike_event_factory() -> Callable[[float, float, float, str], EventInjection]:
    """Build a NETWORK_SPIKE event targeting an edge."""

    def _make(
        t_start: float,
        t_end: float,
        spike_s: float,
        edge_id: str = "client-to-lb",
    ) -> EventInjection:
        return EventInjection(
            event_id="spike",
            target_id=edge_id,
            start={
                "kind": EventDescription.NETWORK_SPIKE_START,
                "t_start": t_start,
                "spike_s": spike_s,
            },
            end={"kind": EventDescription.NETWORK_SPIKE_END, "t_end": t_end},
        )

    return _make


@pytest.fixture
def outage_event_factory() -> Callable[[float, float, str], EventInjection]:
    """Build a SERVER_DOWN/UP interval targeting a server."""

    def _make(
        t_start: float,
        t_end: float,
        server_id: str = "srv-1",
    ) -> EventInjection:
        return EventInjection(
            event_id="outage",
            target_id=server_id,
            start={"kind": EventDescription.SERVER_DOWN, "t_start": t_start},
            end={"kind": EventDescription.SERVER_UP, "t_end": t_end},
        )

    return _make


# --------------------------------------------------------------------------- #
# Payload helpers                                                             #
# --------------------------------------------------------------------------- #

@pytest.fixture
def make_payload() -> Callable[
    [ArrivalsGenerator, TopologyGraph, SimulationSettings, list[EventInjection] | None],
    SimulationPayload,
]:
    """Factory that assembles a validated :class:`SimulationPayload`."""

    def _factory(
        arrivals: ArrivalsGenerator,
        topo: TopologyGraph,
        sim: SimulationSettings,
        events: list[EventInjection] | None = None,
    ) -> SimulationPayload:
        return SimulationPayload(
            arrivals=arrivals,
            topology_graph=topo,
            sim_settings=sim,
            events=events,
        )

    return _factory


@pytest.fixture
def payload_base(
    arrivals_poisson: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> SimulationPayload:
    """
    Minimal payload: generator + client node, no servers/LB, no edges.

    Useful for smoke tests that patch out edges and only exercise the
    runner's boot/shutdown paths.
    """
    nodes = TopologyNodes(servers=[], client=Client(id="client-1"))
    topo = TopologyGraph(nodes=nodes, edges=[])
    return SimulationPayload(
        arrivals=arrivals_poisson,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=None,
    )
