"""Unit tests for the SimulationPayload Pydantic model.

This suite verifies:
- Unique event IDs constraint.
- Target existence against the topology graph.
- Event times inside the simulation horizon.
- Kind/target compatibility (server vs. edge).
- Global liveness: not all servers down simultaneously.

All tests are ruff- and mypy-friendly (short lines, precise raises, and
single statements inside raises blocks). They reuse fixtures from
conftest.py where convenient and build custom topologies when needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from asyncflow.config.constants import Distribution, EventDescription
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import End, EventInjection, Start
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    Server,
    TopologyNodes,
)

if TYPE_CHECKING:
    from asyncflow.schemas.settings.simulation import SimulationSettings
    from asyncflow.schemas.workload.rqs_generator import RqsGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_network_spike(
    event_id: str,
    target_id: str,
    start_t: float,
    end_t: float,
    spike_s: float,
) -> EventInjection:
    """Build a NETWORK_SPIKE event for the given target edge."""
    start = Start(
        kind=EventDescription.NETWORK_SPIKE_START,
        t_start=start_t,
        spike_s=spike_s,
    )
    end = End(kind=EventDescription.NETWORK_SPIKE_END, t_end=end_t)
    return EventInjection(
        event_id=event_id,
        target_id=target_id,
        start=start,
        end=end,
    )


def _mk_server_window(
    event_id: str,
    target_id: str,
    start_t: float,
    end_t: float,
) -> EventInjection:
    """Build a SERVER_DOWN → SERVER_UP event for the given server."""
    start = Start(kind=EventDescription.SERVER_DOWN, t_start=start_t)
    end = End(kind=EventDescription.SERVER_UP, t_end=end_t)
    return EventInjection(
        event_id=event_id,
        target_id=target_id,
        start=start,
        end=end,
    )


def _topology_with_min_edge() -> TopologyGraph:
    """Create a tiny topology with one client and one minimal edge."""
    client = Client(id="client-1")
    edge = Edge(
        id="gen-to-client",
        source="rqs-1",
        target="client-1",
        latency=RVConfig(mean=0.001, distribution=Distribution.POISSON),
    )
    nodes = TopologyNodes(servers=[], client=client)
    return TopologyGraph(nodes=nodes, edges=[edge])


def _topology_with_two_servers_and_edge() -> TopologyGraph:
    """Create a topology with two servers and a minimal edge."""
    client = Client(id="client-1")
    servers = [
    Server(id="srv-1", server_resources={"cpu_cores": 1}, endpoints=[]),
    Server(id="srv-2", server_resources={"cpu_cores": 1}, endpoints=[]),
]
    edge = Edge(
        id="gen-to-client",
        source="rqs-1",
        target="client-1",
        latency=RVConfig(mean=0.001, distribution=Distribution.POISSON),
    )
    nodes = TopologyNodes(servers=servers, client=client)
    return TopologyGraph(nodes=nodes, edges=[edge])


# ---------------------------------------------------------------------------
# Unique event IDs
# ---------------------------------------------------------------------------


def test_unique_event_ids_ok(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """Different event_id values should validate."""
    topo = _topology_with_min_edge()
    ev1 = _mk_network_spike(
        "ev-a", "gen-to-client", start_t=0.0, end_t=1.0, spike_s=0.001,
    )
    ev2 = _mk_network_spike(
        "ev-b", "gen-to-client", start_t=2.0, end_t=3.0, spike_s=0.002,
    )
    payload = SimulationPayload(
        rqs_input=rqs_input,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=[ev1, ev2],
    )
    assert payload.events is not None
    assert len(payload.events) == 2


def test_duplicate_event_ids_rejected(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """Duplicate event_id values must be rejected."""
    topo = _topology_with_min_edge()
    ev1 = _mk_network_spike(
        "ev-dup", "gen-to-client", start_t=0.0, end_t=1.0, spike_s=0.001,
    )
    ev2 = _mk_network_spike(
        "ev-dup", "gen-to-client", start_t=2.0, end_t=3.0, spike_s=0.002,
    )
    with pytest.raises(ValueError, match=r"must be unique"):
        SimulationPayload(
            rqs_input=rqs_input,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev1, ev2],
        )


# ---------------------------------------------------------------------------
# Target existence
# ---------------------------------------------------------------------------


def test_target_id_must_exist(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """Target IDs not present in the topology must be rejected."""
    topo = _topology_with_min_edge()
    ev = _mk_network_spike(
        "ev-x", "missing-edge", start_t=0.0, end_t=1.0, spike_s=0.001,
    )
    with pytest.raises(ValueError, match=r"does not exist"):
        SimulationPayload(
            rqs_input=rqs_input,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


# ---------------------------------------------------------------------------
# Event times within horizon
# ---------------------------------------------------------------------------


def test_start_time_exceeds_horizon_rejected(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """Start time greater than the horizon must be rejected."""
    topo = _topology_with_min_edge()
    horizon = float(sim_settings.total_simulation_time)
    ev = _mk_network_spike(
        "ev-hz-start",
        "gen-to-client",
        start_t=horizon + 0.1,
        end_t=horizon + 0.2,
        spike_s=0.001,
    )
    with pytest.raises(ValueError, match=r"exceeds simulation horizon"):
        SimulationPayload(
            rqs_input=rqs_input,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


def test_end_time_exceeds_horizon_rejected(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """End time greater than the horizon must be rejected."""
    topo = _topology_with_min_edge()
    horizon = float(sim_settings.total_simulation_time)
    ev = _mk_network_spike(
        "ev-hz-end",
        "gen-to-client",
        start_t=horizon - 0.1,
        end_t=horizon + 0.1,
        spike_s=0.001,
    )
    with pytest.raises(ValueError, match=r"exceeds simulation horizon"):
        SimulationPayload(
            rqs_input=rqs_input,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


# ---------------------------------------------------------------------------
# Kind/target compatibility
# ---------------------------------------------------------------------------


def test_server_event_cannot_target_edge(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """SERVER_DOWN should not target an edge ID."""
    topo = _topology_with_min_edge()
    ev = _mk_server_window(
        "ev-srv-bad",
        target_id="gen-to-client",
        start_t=0.0,
        end_t=1.0,
    )
    with pytest.raises(ValueError, match=r"regarding a server .* compatible"):
        SimulationPayload(
            rqs_input=rqs_input,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


def test_edge_event_ok_on_edge(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """NETWORK_SPIKE event is valid when it targets an edge ID."""
    topo = _topology_with_min_edge()
    ev = _mk_network_spike(
        "ev-edge-ok", "gen-to-client", start_t=0.0, end_t=1.0, spike_s=0.001,
    )
    payload = SimulationPayload(
        rqs_input=rqs_input,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=[ev],
    )
    assert payload.events is not None
    assert payload.events[0].target_id == "gen-to-client"


# ---------------------------------------------------------------------------
# Global liveness: not all servers down simultaneously
# ---------------------------------------------------------------------------


def test_reject_when_all_servers_down_at_same_time(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """
    It should raise a ValidationError if there is any time interval during which
    all servers are scheduled to be down simultaneously.
    """
    topo = _topology_with_two_servers_and_edge()

    # --- SETUP: Use a longer simulation horizon for this specific test ---
    # The default `sim_settings` fixture has a short horizon (e.g., 5s) to
    # keep most tests fast. For this test, we need a longer horizon to
    # ensure the event times themselves are valid.
    sim_settings.total_simulation_time = 30  # e.g., 30 seconds

    # The event times are now valid within the new horizon.
    # srv-1 is down [10, 20), srv-2 is down [15, 25).
    # This creates an overlap in [15, 20) where both are down.
    ev_a = _mk_server_window("ev-a", "srv-1", start_t=10.0, end_t=20.0)
    ev_b = _mk_server_window("ev-b", "srv-2", start_t=15.0, end_t=25.0)

    # Now the test will bypass the time horizon validation and trigger
    # the correct validator that checks for server downtime overlap.
    with pytest.raises(ValueError, match=r"all servers are down"):
        SimulationPayload(
            rqs_input=rqs_input,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev_a, ev_b],
        )


def test_accept_when_never_all_down(
    rqs_input: RqsGenerator, sim_settings: SimulationSettings,
) -> None:
    """Payload is valid when at least one server stays up at all times."""
    topo = _topology_with_two_servers_and_edge()

    # --- SETUP: Use a longer simulation horizon for this specific test ---
    # As before, we need to ensure the event times are valid within the
    # simulation's total duration.
    sim_settings.total_simulation_time = 30 # e.g., 30 seconds

    # Staggered windows: srv-1 down [10, 15), srv-2 down [15, 20).
    # There is no point in time where both are down.
    ev_a = _mk_server_window("ev-a", "srv-1", start_t=10.0, end_t=15.0)
    ev_b = _mk_server_window("ev-b", "srv-2", start_t=15.0, end_t=20.0)

    # This should now pass validation without raising an error.
    payload = SimulationPayload(
        rqs_input=rqs_input,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=[ev_a, ev_b],
    )
    assert payload.events is not None
    assert len(payload.events) == 2
