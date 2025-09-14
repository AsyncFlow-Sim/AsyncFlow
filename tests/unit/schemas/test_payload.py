"""Unit tests for the SimulationPayload Pydantic model.

This suite verifies:
- Unique event IDs constraint.
- Target existence against the topology graph.
- Event times inside the simulation horizon.
- Kind/target compatibility (server vs. edge).
- Global liveness: not all servers down simultaneously.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from tests.unit.helpers import make_min_ep

from asyncflow.config.enums import Distribution, EventDescription
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import End, EventInjection, Start
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import Client, Server, TopologyNodes

if TYPE_CHECKING:
    from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
    from asyncflow.schemas.settings.simulation import SimulationSettings


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
        Server(
            id="srv-1",
            server_resources={"cpu_cores": 1},
            endpoints=[make_min_ep()],
        ),
        Server(
            id="srv-2",
            server_resources={"cpu_cores": 1},
            endpoints=[make_min_ep()],
        ),
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
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
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
        arrivals=arrivals_gen,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=[ev1, ev2],
    )
    assert payload.events is not None
    assert len(payload.events) == 2


def test_duplicate_event_ids_rejected(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
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
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev1, ev2],
        )


# ---------------------------------------------------------------------------
# Target existence
# ---------------------------------------------------------------------------


def test_target_id_must_exist(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """Target IDs not present in the topology must be rejected."""
    topo = _topology_with_min_edge()
    ev = _mk_network_spike(
        "ev-x", "missing-edge", start_t=0.0, end_t=1.0, spike_s=0.001,
    )
    with pytest.raises(ValueError, match=r"does not exist"):
        SimulationPayload(
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


# ---------------------------------------------------------------------------
# Event times within horizon
# ---------------------------------------------------------------------------


def test_start_time_exceeds_horizon_rejected(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
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
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


def test_end_time_exceeds_horizon_rejected(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
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
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


# ---------------------------------------------------------------------------
# Kind/target compatibility
# ---------------------------------------------------------------------------


def test_server_event_cannot_target_edge(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
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
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev],
        )


def test_edge_event_ok_on_edge(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """NETWORK_SPIKE event is valid when it targets an edge ID."""
    topo = _topology_with_min_edge()
    ev = _mk_network_spike(
        "ev-edge-ok", "gen-to-client", start_t=0.0, end_t=1.0, spike_s=0.001,
    )
    payload = SimulationPayload(
        arrivals=arrivals_gen,
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
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """Raise if there exists an interval during which all servers are down"""
    topo = _topology_with_two_servers_and_edge()
    sim_settings.total_simulation_time = 30

    # Overlap: both down on [15, 20).
    ev_a = _mk_server_window("ev-a", "srv-1", start_t=10.0, end_t=20.0)
    ev_b = _mk_server_window("ev-b", "srv-2", start_t=15.0, end_t=25.0)

    with pytest.raises(ValueError, match=r"all servers are down"):
        SimulationPayload(
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev_a, ev_b],
        )


def test_accept_when_never_all_down(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """Valid when at least one server stays up at any time."""
    topo = _topology_with_two_servers_and_edge()
    sim_settings.total_simulation_time = 30

    # Staggered windows: never both down at once.
    ev_a = _mk_server_window("ev-a", "srv-1", start_t=10.0, end_t=15.0)
    ev_b = _mk_server_window("ev-b", "srv-2", start_t=15.0, end_t=20.0)

    payload = SimulationPayload(
        arrivals=arrivals_gen,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=[ev_a, ev_b],
    )
    assert payload.events is not None
    assert len(payload.events) == 2


def test_server_outage_back_to_back_is_valid(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """Back-to-back outages on the same server must be accepted."""
    topo = _topology_with_two_servers_and_edge()
    sim_settings.total_simulation_time = 30

    ev_a = _mk_server_window("ev-a", "srv-1", start_t=10.0, end_t=15.0)
    ev_b = _mk_server_window("ev-b", "srv-1", start_t=15.0, end_t=20.0)

    payload = SimulationPayload(
        arrivals=arrivals_gen,
        topology_graph=topo,
        sim_settings=sim_settings,
        events=[ev_a, ev_b],
    )
    assert payload.events is not None
    assert len(payload.events) == 2


def test_server_outage_overlap_same_server_is_rejected(
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """Overlapping outages on the same server must be rejected."""
    topo = _topology_with_two_servers_and_edge()
    sim_settings.total_simulation_time = 30

    ev_a = _mk_server_window("ev-a", "srv-1", start_t=10.0, end_t=15.0)
    ev_b = _mk_server_window("ev-b", "srv-1", start_t=14.0, end_t=20.0)

    with pytest.raises(ValueError, match=r"Overlapping events for"):
        SimulationPayload(
            arrivals=arrivals_gen,
            topology_graph=topo,
            sim_settings=sim_settings,
            events=[ev_a, ev_b],
        )
