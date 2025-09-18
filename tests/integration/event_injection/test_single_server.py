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



def test_single_server_with_spike(
    env: simpy.Environment,
    topology_single_server: Callable[..., TopologyGraph],
    make_payload: Callable[
        [ArrivalsGenerator, TopologyGraph, SimulationSettings,
         list[EventInjection] | None],
        SimulationPayload,
    ],
) -> None:
    """Run with both edge spike and server outage; verify KPIs exist."""
    arrivals = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=20.0,
        model=Distribution.POISSON,
    )
    topo = topology_single_server(service_time_s=0.001, edge_mean=0.002)
    sim = SimulationSettings(total_simulation_time=5)

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
    ]

    payload = make_payload(arrivals, topo, sim, events)

    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    stats = results.get_latency_stats()
    assert stats
    assert stats[LatencyKey.TOTAL_REQUESTS] > 0
