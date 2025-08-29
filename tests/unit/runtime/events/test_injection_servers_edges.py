"""Mixed timeline tests: edge spikes and server outages in the same run."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

import pytest
import simpy

from asyncflow.config.constants import EventDescription
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.events.injection import EventInjectionRuntime
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.nodes import Server, ServerResources

if TYPE_CHECKING:
    from asyncflow.schemas.settings.simulation import SimulationSettings


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _edge(edge_id: str, source: str, target: str) -> Edge:
    """Create a minimal edge with negligible latency."""
    return Edge(id=edge_id, source=source, target=target, latency=RVConfig(mean=0.001))


def _srv(server_id: str) -> Server:
    """Create a minimal, fully-typed Server instance for tests."""
    return Server(id=server_id, server_resources=ServerResources(), endpoints=[])


def _spike_event(
    *, ev_id: str,
    edge_id: str,
    t0: float,
    t1: float,
    spike_s: float,
    ) -> EventInjection:
    """Build a NETWORK_SPIKE_START → NETWORK_SPIKE_END event for an edge."""
    return EventInjection(
        event_id=ev_id,
        target_id=edge_id,
        start={
            "kind": EventDescription.NETWORK_SPIKE_START,
            "t_start": t0,
            "spike_s": spike_s,
        },
        end={"kind": EventDescription.NETWORK_SPIKE_END, "t_end": t1},
    )


def _srv_event(server_id: str, ev_id: str, t0: float, t1: float) -> EventInjection:
    """Build a SERVER_DOWN → SERVER_UP event for a server."""
    return EventInjection(
        event_id=ev_id,
        target_id=server_id,
        start={"kind": EventDescription.SERVER_DOWN, "t_start": t0},
        end={"kind": EventDescription.SERVER_UP, "t_end": t1},
    )


def _drain_zero_time(env: simpy.Environment) -> None:
    """Consume all events at the current time (typically t=0)."""
    while env.peek() == env.now:
        env.step()


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #

def test_edge_spike_and_server_outage_independent_timelines(
    env: simpy.Environment, sim_settings: SimulationSettings,
) -> None:
    """Edge spikes evolve independently from server outages on LB edges."""
    # Topology pieces:
    net_e = _edge("net-1", "X", "Y")  # edge that will receive the spike
    lb_e1 = _edge("lb-e1", "lb-1", "srv-1")
    lb_e2 = _edge("lb-e2", "lb-1", "srv-2")

    # Edge runtimes only for LB edges (spike is handled by injection runtime state)
    er1 = EdgeRuntime(
        env=env,
        edge_config=lb_e1,
        target_box=simpy.Store(env),
        settings=sim_settings,
    )
    er2 = EdgeRuntime(
        env=env,
        edge_config=lb_e2,
        target_box=simpy.Store(env),
        settings=sim_settings,
        )
    lb_out = OrderedDict[str, EdgeRuntime]([("lb-e1", er1), ("lb-e2", er2)])

    # Events:
    # - Server outage on srv-1: [1.0, 3.0] → lb-e1 removed at 1.0, reinserted at 3.0.
    # - Edge spike on net-1:   [2.0, 4.0] → +0.3 during [2.0, 4.0].
    ev_srv = _srv_event("srv-1", "out-1", 1.0, 3.0)
    ev_spk = _spike_event(
        ev_id="spk-1", edge_id="net-1", t0=2.0, t1=4.0, spike_s=0.3,
        )

    inj = EventInjectionRuntime(
        events=[ev_srv, ev_spk],
        edges=[net_e],
        env=env,
        servers=[_srv("srv-1"), _srv("srv-2")],
        lb_out_edges=lb_out,
    )
    inj.start()

    _drain_zero_time(env)
    assert list(lb_out.keys()) == ["lb-e1", "lb-e2"]
    assert inj.edges_spike.get("net-1", 0.0) == pytest.approx(0.0)

    # @1.0 → server DOWN (srv-1) → remove lb-e1
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(1.0)
    assert list(lb_out.keys()) == ["lb-e2"]
    assert "lb-e1" not in lb_out
    assert inj.edges_spike.get("net-1", 0.0) == pytest.approx(0.0)

    # @2.0 → spike START on net-1 → +0.3
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(2.0)
    assert inj.edges_spike.get("net-1", 0.0) == pytest.approx(0.3)
    assert list(lb_out.keys()) == ["lb-e2"]  # still down for srv-1

    # @3.0 → server UP (srv-1) → reinsert lb-e1 at the end
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(3.0)
    assert list(lb_out.keys()) == ["lb-e2", "lb-e1"]
    assert inj.edges_spike.get("net-1", 0.0) == pytest.approx(0.3)

    # @4.0 → spike END on net-1 → 0.0
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(4.0)
    assert inj.edges_spike.get("net-1", 0.0) == pytest.approx(0.0)


def test_interleaved_multiple_spikes_with_single_outage(
    env: simpy.Environment, sim_settings: SimulationSettings,
) -> None:
    """Multiple spikes can interleave with a single outage on a different component."""
    # Components:
    net_e = _edge("net-2", "S", "T")
    lb_e1 = _edge("lb-e1", "lb-1", "srv-1")
    lb_e2 = _edge("lb-e2", "lb-1", "srv-2")

    er1 = EdgeRuntime(
        env=env,
        edge_config=lb_e1,
        target_box=simpy.Store(env),
        settings=sim_settings,
        )
    er2 = EdgeRuntime(
        env=env,
        edge_config=lb_e2,
        target_box=simpy.Store(env),
        settings=sim_settings,
        )
    lb_out = OrderedDict[str, EdgeRuntime]([("lb-e1", er1), ("lb-e2", er2)])

    # Events timeline no equal timestamps across server/edge to
    # avoid cross-process order assumptions):
    #   1.0  server DOWN (srv-1)                 → remove lb-e1
    #   2.0  spike A START on net-2 (+0.2)       → +0.2
    #   3.0  server UP (srv-1)                   → reinsert lb-e1 at the end
    #   4.0  spike B START on net-2 (+0.1)       → +0.3
    #   5.0  spike A END on net-2                → +0.1
    #   6.0  spike B END on net-2                → +0.0
    ev_down = _srv_event("srv-1", "out-1", 1.0, 3.0)
    spk_a = _spike_event(ev_id="spk-A", edge_id="net-2", t0=2.0, t1=5.0, spike_s=0.2)
    spk_b = _spike_event(ev_id="spk-B", edge_id="net-2", t0=4.0, t1=6.0, spike_s=0.1)

    inj = EventInjectionRuntime(
        events=[ev_down, spk_a, spk_b],
        edges=[net_e],
        env=env,
        servers=[_srv("srv-1"), _srv("srv-2")],
        lb_out_edges=lb_out,
    )
    inj.start()

    _drain_zero_time(env)
    assert list(lb_out.keys()) == ["lb-e1", "lb-e2"]
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.0)

   # @1.0 server DOWN → remove lb-e1
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(1.0)
    assert list(lb_out.keys()) == ["lb-e2"]
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.0)

    # @2.0 spike A START → +0.2
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(2.0)
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.2)
    assert list(lb_out.keys()) == ["lb-e2"]

    # @3.0 server UP → reinsert lb-e1 at the end
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(3.0)
    assert list(lb_out.keys()) == ["lb-e2", "lb-e1"]
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.2)

    # @4.0 spike B START → +0.3
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(4.0)
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.3)

    # @5.0 spike A END → +0.1
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(5.0)
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.1)

    # @6.0 spike B END → +0.0
    env.step()
    _drain_zero_time(env)
    assert env.now == pytest.approx(6.0)
    assert inj.edges_spike.get("net-2", 0.0) == pytest.approx(0.0)

