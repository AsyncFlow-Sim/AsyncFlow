"""Integration test: single server with edge spike and server outage.

Topology:

  rqs-1 → client-1 → lb-1 → srv-1
                      srv-1 → client-1

Events:
- NETWORK_SPIKE on 'client-to-lb' during a small window.
- SERVER_DOWN/UP on 'srv-1' during a small window.

Assertions focus on end-to-end KPIs; the fine-grained event sequencing is
covered by unit tests in the event injection suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import simpy

from asyncflow.config.constants import Distribution, EventDescription, LatencyKey
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
from asyncflow.schemas.workload.rqs_generator import RqsGenerator

if TYPE_CHECKING:
    from asyncflow.metrics.analyzer import ResultsAnalyzer


def _server(sid: str) -> Server:
    return Server(id=sid, server_resources=ServerResources(), endpoints=[])


def _edge(eid: str, src: str, tgt: str, mean: float = 0.002) -> Edge:
    return Edge(
        id=eid,
        source=src,
        target=tgt,
        latency=RVConfig(mean=mean, distribution=Distribution.POISSON),
    )


def test_single_server_with_spike_and_outage_end_to_end() -> None:
    """Run with both edge spike and server outage; verify KPIs exist."""
    env = simpy.Environment()
    rqs = RqsGenerator(
        id="rqs-1",
        avg_active_users=RVConfig(mean=1.0),
        avg_request_per_minute_per_user=RVConfig(mean=2.0),
        user_sampling_window=10.0,
    )
    sim = SimulationSettings(total_simulation_time=1.0)

    client = Client(id="client-1")
    lb = LoadBalancer(id="lb-1")
    srv = _server("srv-1")

    edges = [
        _edge("gen-to-client", "rqs-1", "client-1"),
        _edge("client-to-lb", "client-1", "lb-1"),
        _edge("lb-to-srv1", "lb-1", "srv-1"),
        _edge("srv1-to-client", "srv-1", "client-1"),
    ]
    nodes = TopologyNodes(servers=[srv], client=client, load_balancer=lb)
    topo = TopologyGraph(nodes=nodes, edges=edges)

    # Events in a short (but disjoint) schedule to avoid cross-process ties
    events = [
        EventInjection(
            event_id="spike",
            target_id="client-to-lb",
            start={
                "kind": EventDescription.NETWORK_SPIKE_START,
                "t_start": 0.2,
                "spike_s": 0.01,
            },
            end={"kind": EventDescription.NETWORK_SPIKE_END, "t_end": 0.4},
        ),
        EventInjection(
            event_id="outage",
            target_id="srv-1",
            start={"kind": EventDescription.SERVER_DOWN, "t_start": 0.5},
            end={"kind": EventDescription.SERVER_UP, "t_end": 0.7},
        ),
    ]

    payload = SimulationPayload(rqs_input=rqs, topology_graph=topo, sim_settings=sim)
    payload.events = events

    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    stats = results.get_latency_stats()
    assert stats
    assert stats[LatencyKey.TOTAL_REQUESTS] > 0
