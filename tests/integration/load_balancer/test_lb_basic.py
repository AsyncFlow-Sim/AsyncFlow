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

from asyncflow.config.enums import (
    Distribution,
    LatencyKey,
    SampledMetricName,
)
from asyncflow.runner.simulation import SimulationRunner
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.settings.simulation import SimulationSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    import simpy

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
    from asyncflow.schemas.payload import SimulationPayload
    from asyncflow.schemas.topology.graph import TopologyGraph


def test_lb_two_servers_end_to_end_smoke(
    env: simpy.Environment,
    topology_two_servers: Callable[..., TopologyGraph],
    make_payload: Callable[
        [ArrivalsGenerator, TopologyGraph, SimulationSettings, None],
        SimulationPayload,
    ],
) -> None:
    """Run end-to-end with LB and two servers; check basic KPIs exist."""
    arrivals = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=20.0,
        model=Distribution.POISSON,
    )

    # Horizon must be >= 5 (schema), use a bit more to accumulate samples.
    sim = SimulationSettings(total_simulation_time=8.0)

    # Topology: rqs→client→lb→srv{1,2} and back srv→client
    topo = topology_two_servers(service_time_s=0.001, edge_mean=0.001)

    payload = make_payload(arrivals, topo, sim, None)

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
