"""Integration test: LB with two servers and concurrent event injections.

Topology:
  rqs-1 → client-1 → lb-1 → {srv-1, srv-2}
                     srv-* → client-1

Events:
- NETWORK_SPIKE on 'client-to-lb' in [0.20, 0.35].
- SERVER_DOWN/UP on 'srv-1' in [0.40, 0.55].

Assertions:
- Simulation completes.
- Latency stats and throughput exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from asyncflow.config.enums import Distribution, EventDescription, LatencyKey
from asyncflow.runner.simulation import SimulationRunner
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.settings.simulation import SimulationSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    import simpy

    from asyncflow.metrics.simulation_analyzer import ResultsAnalyzer
    from asyncflow.schemas.payload import SimulationPayload
    from asyncflow.schemas.topology.graph import TopologyGraph


def test_lb_two_servers_with_events_end_to_end(
    env: simpy.Environment,
    topology_two_servers: Callable[[float | None, float], TopologyGraph],
    make_payload: Callable[
        [ArrivalsGenerator, TopologyGraph, SimulationSettings,
         list[EventInjection] | None],
        SimulationPayload,
    ],
) -> None:
    """Round-robin LB with events; check that KPIs are produced."""
    arrivals = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=20.0,
        model=Distribution.POISSON,
    )
    topo = topology_two_servers(service_time_s=0.001, edge_mean=0.002)
    sim = SimulationSettings(total_simulation_time=5)

    events = [
        EventInjection(
            event_id="spike",
            target_id="client-to-lb",
            start={
                "kind": EventDescription.NETWORK_SPIKE_START,
                "t_start": 0.20,
                "spike_s": 0.02,
            },
            end={"kind": EventDescription.NETWORK_SPIKE_END, "t_end": 0.35},
        ),
        EventInjection(
            event_id="outage-srv1",
            target_id="srv-1",
            start={"kind": EventDescription.SERVER_DOWN, "t_start": 0.40},
            end={"kind": EventDescription.SERVER_UP, "t_end": 0.55},
        ),
    ]

    payload = make_payload(arrivals, topo, sim, events)

    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    stats = results.get_latency_stats()
    assert stats
    assert stats[LatencyKey.TOTAL_REQUESTS] > 0
    ts, rps = results.get_throughput_series()
    assert len(ts) == len(rps) > 0
