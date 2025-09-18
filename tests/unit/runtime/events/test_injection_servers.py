"""Server-outage tests for EventInjectionRuntime (using real `Server` model)."""

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
    """Create a minimal LB→server edge with negligible latency."""
    return Edge(
        id=edge_id,
        source=source,
        target=target,
        latency=RVConfig(mean=0.001),
    )


def _srv(server_id: str) -> Server:
    """Create a minimal, fully-typed Server instance for tests."""
    return Server(
        id=server_id,
        server_resources=ServerResources(),  # uses defaults
        endpoints=[],                        # empty list is valid
    )

def _srv_event(
    server_id: str, ev_id: str, t_start: float, t_end: float) -> EventInjection:
    """Create a SERVER_DOWN/UP event for the given server id."""
    return EventInjection(
        event_id=ev_id,
        target_id=server_id,
        start={"kind": EventDescription.SERVER_DOWN, "t_start": t_start},
        end={"kind": EventDescription.SERVER_UP, "t_end": t_end},
    )


def _drain_zero_time(env: simpy.Environment) -> None:
    """Consume all events scheduled at the current time (typically t=0)."""
    while env.peek() == env.now:
        env.step()


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #

def test_outage_removes_and_restores_edge_order(
    env: simpy.Environment, sim_settings: SimulationSettings,
) -> None:
    """DOWN removes the LB→server edge; reinserts it at the end (OrderedDict policy)"""
    # Two distinct LB→server edges
    lb_e1 = _edge("lb-e1", "lb-1", "srv-1")
    lb_e2 = _edge("lb-e2", "lb-1", "srv-2")

    er1 = EdgeRuntime(
        env=env, edge_config=lb_e1, target_box=simpy.Store(env), settings=sim_settings,
        )
    er2 = EdgeRuntime(
        env=env, edge_config=lb_e2, target_box=simpy.Store(env), settings=sim_settings,
        )

    lb_out = OrderedDict[str, EdgeRuntime]([("lb-e1", er1), ("lb-e2", er2)])

    outage = _srv_event("srv-1", "ev-out", 5.0, 7.0)
    servers = [_srv("srv-1"), _srv("srv-2")]

    inj = EventInjectionRuntime(
        events=[outage], edges=[], env=env, servers=servers, lb_out_edges=lb_out,
        )
    inj.start()

    _drain_zero_time(env)
    assert list(lb_out.keys()) == ["lb-e1", "lb-e2"]

    # @5.0 → remove lb-e1
    env.step()
    assert env.now == pytest.approx(5.0)
    assert list(lb_out.keys()) == ["lb-e2"]
    assert "lb-e1" not in lb_out

    # @7.0 → reinsert lb-e1 at the end
    env.step()
    assert env.now == pytest.approx(7.0)
    assert list(lb_out.keys()) == ["lb-e2", "lb-e1"]
    assert lb_out["lb-e1"] is er1


def test_outage_for_server_not_in_lb_is_noop(
    env: simpy.Environment, sim_settings: SimulationSettings,
) -> None:
    """DOWN/UP for a server with no LB edges should not change the LB mapping."""
    lb_e2 = _edge("lb-e2", "lb-1", "srv-2")
    er2 = EdgeRuntime(
        env=env, edge_config=lb_e2, target_box=simpy.Store(env), settings=sim_settings)
    lb_out = OrderedDict[str, EdgeRuntime]([("lb-e2", er2)])

    outage = _srv_event("srv-3", "ev-out", 5.0, 6.0)  # srv-3 not in LB
    inj = EventInjectionRuntime(
        events=[outage],
        edges=[],
        env=env,
        servers=[_srv("srv-2"), _srv("srv-3")],
        lb_out_edges=lb_out,
    )
    inj.start()

    _drain_zero_time(env)
    assert list(lb_out.keys()) == ["lb-e2"]

    env.step()  # @5.0
    assert list(lb_out.keys()) == ["lb-e2"]

    env.step()  # @6.0
    assert list(lb_out.keys()) == ["lb-e2"]
