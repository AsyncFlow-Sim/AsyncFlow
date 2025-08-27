"""Integration test: one LB and two servers (round-robin by default).

We build a minimal but functional topology:

  rqs-1 → client-1 → lb-1 → {srv-1, srv-2}
                     srv-* → client-1

Assertions:
- Simulation completes without error.
- Latency stats and throughput time-series are non-empty.
- Sampled metrics include edge/server series.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import simpy

from asyncflow.config.constants import Distribution, LatencyKey, SampledMetricName
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.endpoint import Endpoint  # noqa: F401
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    Server,
    ServerResources,
    TopologyNodes,
)
from asyncflow.schemas.workload.rqs_generator import RqsGenerator
from asyncflow.config.constants import EndpointStepCPU, StepOperation
from asyncflow.schemas.topology.endpoint import Endpoint, Step
from asyncflow.schemas.topology.nodes import Server, ServerResources

if TYPE_CHECKING:
    from asyncflow.metrics.analyzer import ResultsAnalyzer


def _server(server_id: str) -> Server:
    """Minimal server with a single CPU-bound endpoint."""
    ep = Endpoint(
        endpoint_name="get",
        steps=[
            Step(
                kind=EndpointStepCPU.CPU_BOUND_OPERATION,
                step_operation={StepOperation.CPU_TIME: 0.001},
            )
        ],
    )
    return Server(
        id=server_id,
        server_resources=ServerResources(),  # defaults are fine
        endpoints=[ep],
    )


def _edge(eid: str, src: str, tgt: str, mean: float = 0.001) -> Edge:
    """Low-latency edge to keep tests fast/deterministic enough."""
    return Edge(
        id=eid,
        source=src,
        target=tgt,
        latency=RVConfig(mean=mean, distribution=Distribution.POISSON),
    )


def test_lb_two_servers_end_to_end_smoke() -> None:
    """Run end-to-end with LB and two servers; check basic KPIs exist."""
    env = simpy.Environment()

    # Stronger workload to avoid empty stats due to randomness:
    # ~5 active users generating ~60 rpm each → ~5 rps expected.
    rqs = RqsGenerator(
        id="rqs-1",
        avg_active_users=RVConfig(mean=5.0),
        avg_request_per_minute_per_user=RVConfig(mean=60.0),
        user_sampling_window=5.0,
    )
    # Horizon must be >= 5 (schema), use a bit more to accumulate samples.
    sim = SimulationSettings(total_simulation_time=8.0)

    # Topology: rqs→client→lb→srv{1,2} and back srv→client
    client = Client(id="client-1")
    lb = LoadBalancer(id="lb-1")

    srv1 = _server("srv-1")
    srv2 = _server("srv-2")

    edges = [
        _edge("gen-to-client", "rqs-1", "client-1"),
        _edge("client-to-lb", "client-1", "lb-1"),
        _edge("lb-to-srv1", "lb-1", "srv-1"),
        _edge("lb-to-srv2", "lb-1", "srv-2"),
        _edge("srv1-to-client", "srv-1", "client-1"),
        _edge("srv2-to-client", "srv-2", "client-1"),
    ]
    nodes = TopologyNodes(servers=[srv1, srv2], client=client, load_balancer=lb)
    topo = TopologyGraph(nodes=nodes, edges=edges)

    payload = SimulationPayload(rqs_input=rqs, topology_graph=topo, sim_settings=sim)

    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    # Assertions: latency and throughput are present
    stats = results.get_latency_stats()
    assert stats
    assert stats[LatencyKey.TOTAL_REQUESTS] > 0
    assert stats[LatencyKey.MEAN] > 0.0

    ts, rps = results.get_throughput_series()
    assert len(ts) == len(rps) > 0
    assert any(val > 0 for val in rps)

    sampled = results.get_sampled_metrics()
    assert SampledMetricName.RAM_IN_USE in sampled
    assert sampled[SampledMetricName.RAM_IN_USE]
    assert SampledMetricName.EDGE_CONCURRENT_CONNECTION in sampled
    assert sampled[SampledMetricName.EDGE_CONCURRENT_CONNECTION]
