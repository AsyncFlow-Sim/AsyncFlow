"""Step-by-step tests for edge spike handling in EventInjectionRuntime."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

import pytest

from asyncflow.config.constants import EventDescription
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.events.injection import (
    END_MARK,
    START_MARK,
    EventInjectionRuntime,
)
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.topology.edges import Edge

if TYPE_CHECKING:
    import simpy


# ----------------------------- Helpers ------------------------------------- #

def _edge(edge_id: str, source: str, target: str) -> Edge:
    """Minimal edge with negligible latency."""
    return Edge(id=edge_id, source=source, target=target, latency=RVConfig(mean=0.001))


def _spike_event(
    *, event_id: str, edge_id: str, t_start: float, t_end: float, spike_s: float,
) -> EventInjection:
    """NETWORK_SPIKE event for a specific edge."""
    return EventInjection(
        event_id=event_id,
        target_id=edge_id,
        start={
            "kind": EventDescription.NETWORK_SPIKE_START,
            "t_start": t_start,
            "spike_s": spike_s,
        },
        end={"kind": EventDescription.NETWORK_SPIKE_END, "t_end": t_end},
    )


def _drain_zero_time(env: simpy.Environment) -> None:
    """Consume *all* events scheduled at the current time (typically t=0)"""
    while env.peek() == env.now:
        env.step()

# ----------------------------- Tests (edge spike) --------------------------- #

def test_single_spike_start_and_end_step_by_step(env: simpy.Environment) -> None:
    """Single spike: +0.5 at t=1.0, gives 0.0 a t=3.0."""
    edges = [_edge("edge-1", "A", "B")]
    ev = _spike_event(
        event_id="ev1", edge_id="edge-1", t_start=1.0, t_end=3.0, spike_s=0.5,
    )

    rt = EventInjectionRuntime(
        events=[ev],
        edges=edges,
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    rt.start()

    # Drena tutti gli 'start events' a t=0 dei processi registrati
    _drain_zero_time(env)

    # Ora il prossimo evento deve essere a 1.0 (START)
    assert env.peek() == pytest.approx(1.0)

    # Step @1.0 → applica START(ev1)
    env.step()
    assert env.now == pytest.approx(1.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.5)

    # Prossimo evento a 3.0 (END)
    assert env.peek() == pytest.approx(3.0)

    # Step @3.0 → applica END(ev1)
    env.step()
    assert env.now == pytest.approx(3.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.0)


def test_spike_superposition_on_same_edge(env: simpy.Environment) -> None:
    """Due spike sovrapposti si sommano nell'intervallo comune."""
    edges = [_edge("edge-1", "A", "B")]
    ev1 = _spike_event(
        event_id="ev1", edge_id="edge-1", t_start=1.0, t_end=4.0, spike_s=0.3,
    )
    ev2 = _spike_event(
        event_id="ev2", edge_id="edge-1", t_start=2.0, t_end=3.0, spike_s=0.2,
    )

    rt = EventInjectionRuntime(
        events=[ev1, ev2],
        edges=edges,
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    rt.start()

    _drain_zero_time(env)           # next should be 1.0
    env.step()                      # @1.0 START ev1
    assert env.now == pytest.approx(1.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.3)

    env.step()                      # @2.0 START ev2
    assert env.now == pytest.approx(2.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.5)

    env.step()                      # @3.0 END ev2
    assert env.now == pytest.approx(3.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.3)

    env.step()                      # @4.0 END ev1
    assert env.now == pytest.approx(4.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.0)


def test_end_before_start_at_same_timestamp(env: simpy.Environment) -> None:
    """A t=5.0 devono avvenire END(evA) poi START(evB), spike finale 0.6."""
    edges = [_edge("edge-1", "X", "Y")]
    ev_a = _spike_event(
        event_id="evA", edge_id="edge-1", t_start=1.0, t_end=5.0, spike_s=0.4,
    )
    ev_b = _spike_event(
        event_id="evB", edge_id="edge-1", t_start=5.0, t_end=6.0, spike_s=0.6,
    )

    rt = EventInjectionRuntime(
        events=[ev_a, ev_b],
        edges=edges,
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    rt.start()

    _drain_zero_time(env)
    env.step()
    assert env.now == pytest.approx(1.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.4)

    env.step()
    assert env.now == pytest.approx(5.0)
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.6)


def test_only_targeted_edges_are_marked_affected(env: simpy.Environment) -> None:
    """Solo l'edge con evento è marcato e riceve spike."""
    edges = [_edge("edge-1", "A", "B"), _edge("edge-2", "A", "C")]
    ev = _spike_event(
        event_id="ev1", edge_id="edge-1", t_start=1.0, t_end=2.0, spike_s=0.4,
    )

    rt = EventInjectionRuntime(
        events=[ev],
        edges=edges,
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    rt.start()

    assert "edge-1" in rt.edges_affected
    assert "edge-2" not in rt.edges_affected

    _drain_zero_time(env)           # next 1.0
    env.step()                      # @1.0 START ev1
    assert rt.edges_spike.get("edge-1", 0.0) == pytest.approx(0.4)
    assert rt.edges_spike.get("edge-2", 0.0) == pytest.approx(0.0)


def test_internal_timeline_order_at_same_time(env: simpy.Environment) -> None:
    """Controllo diretto della timeline: a 5.0 → [END, START]."""
    edges = [_edge("edge-1", "S", "T")]
    ev_a = _spike_event(
        event_id="a", edge_id="edge-1", t_start=1.0, t_end=5.0, spike_s=0.4,
    )
    ev_b = _spike_event(
        event_id="b", edge_id="edge-1", t_start=5.0, t_end=6.0, spike_s=0.6,
    )

    rt = EventInjectionRuntime(
        events=[ev_a, ev_b],
        edges=edges,
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )

    times_at_5 = [tpl for tpl in rt._edges_timeline if tpl[0] == 5.0]  # noqa: SLF001
    assert len(times_at_5) == 2
    marks_at_5 = [tpl[3] for tpl in times_at_5]
    assert marks_at_5 == [END_MARK, START_MARK]


def test_no_events_is_noop(env: simpy.Environment) -> None:
    """When events=None, the runtime should not alter any edge state."""
    edges = [_edge("e1", "A", "B")]

    inj = EventInjectionRuntime(
        events=None,
        edges=edges,
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    # Should start without scheduling edge changes.
    inj.start()

    assert inj.edges_affected == set()
    assert inj.edges_spike == {}


def test_end_then_multiple_starts_same_timestamp(env: simpy.Environment) -> None:
    """At the same timestamp, END must be applied before multiple STARTs.

    Scenario on edge 'E':
      ev1: +0.4 active [1, 5]
      ev2: +0.3 active [5, 6]
      ev3: +0.2 active [5, 7]

    At t=5.0:
      - END(ev1) applies first (removes +0.4 → 0.0),
      - then START(ev2) and START(ev3) (+0.3 + 0.2),
      Final spike at t=5.0 is +0.5.
    """
    e = _edge("E", "S", "T")
    ev1 = _spike_event(
        event_id="ev1", edge_id=e.id, t_start=1.0, t_end=5.0, spike_s=0.4,
    )
    ev2 = _spike_event(
        event_id="ev2", edge_id=e.id, t_start=5.0, t_end=6.0, spike_s=0.3,
    )
    ev3 = _spike_event(
        event_id="ev3", edge_id=e.id, t_start=5.0, t_end=7.0, spike_s=0.2,
    )

    inj = EventInjectionRuntime(
        events=[ev1, ev2, ev3],
        edges=[e],
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    inj.start()

    _drain_zero_time(env)

    # @1.0 → START ev1 → +0.4
    env.step()
    assert env.now == pytest.approx(1.0)
    assert inj.edges_spike[e.id] == pytest.approx(0.4)

    # @5.0 → END ev1, then START ev2 & START ev3 → 0.0 + 0.3 + 0.2 = 0.5
    env.step()
    assert env.now == pytest.approx(5.0)
    assert inj.edges_spike[e.id] == pytest.approx(0.5)


def test_zero_time_batch_draining_makes_first_event_visible(
    env: simpy.Environment) -> None:
    """After start(), draining zero-time events reveals the first real timestamp.

    Without draining, the next scheduled item may still be an activation at t=0.
    After draining, the next event should be the edge spike START (e.g., 1.0s).
    """
    e = _edge("E", "S", "T")
    ev = _spike_event(event_id="ev", edge_id=e.id, t_start=1.0, t_end=2.0, spike_s=0.1)

    inj = EventInjectionRuntime(
        events=[ev],
        edges=[e],
        env=env,
        servers=[],
        lb_out_edges=OrderedDict[str, EdgeRuntime](),
    )
    inj.start()

    # Drain zero-time activations so the next event is 1.0s.
    _drain_zero_time(env)
    assert env.peek() == pytest.approx(1.0)

    # Step to 1.0s and confirm activation.
    env.step()
    assert env.now == pytest.approx(1.0)
    assert inj.edges_spike[e.id] == pytest.approx(0.1)
