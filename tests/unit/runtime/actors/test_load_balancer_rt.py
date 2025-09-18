"""Unit tests for ``LoadBalancerRuntime`` (round-robin & least-connections)."""

from __future__ import annotations

import math
from collections import OrderedDict
from typing import TYPE_CHECKING, cast

import simpy

from asyncflow.config.enums import LbAlgorithmsName, SystemNodes
from asyncflow.runtime.actors.load_balancer import LoadBalancerRuntime
from asyncflow.schemas.topology.nodes import LoadBalancer

if TYPE_CHECKING:
    from collections.abc import Generator as TypingGenerator

    from asyncflow.runtime.actors.edge import EdgeRuntime


# --------------------------------------------------------------------------- #
# Dummy objects (lightweight test doubles)                                    #
# --------------------------------------------------------------------------- #
class DummyState:
    """Tiny substitute for ``RequestState`` - only ``history`` is needed."""

    def __init__(self) -> None:
        """Inizialization of the attributes"""
        self.history: list[str] = []

    def record_hop(self, comp_type: SystemNodes, comp_id: str, _: float) -> None:
        """Append the hop as ``"<value>:<id>"``."""
        self.history.append(f"{comp_type.value}:{comp_id}")


class DummyEdge:
    """Stub that mimics just the pieces `LoadBalancerRuntime` relies on."""

    def __init__(self, edge_id: str, concurrent: int = 0) -> None:
        """Inizialization of the attributes"""
        self.edge_config = type("Cfg", (), {"id": edge_id})
        self.concurrent_connections = concurrent
        self.received: list[DummyState] = []

    # Signature compatible with EdgeRuntime.transport
    def transport(self, state: DummyState) -> None:
        """Function to simulate the transport"""
        self.received.append(state)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def make_lb_runtime(
    env: simpy.Environment,
    algorithm: LbAlgorithmsName,
    edges: list[DummyEdge],
) -> LoadBalancerRuntime:
    """Wire LB, its inbox store and the supplied dummy edges."""
    lb_cfg = LoadBalancer(
        id="lb-1",
        algorithms=algorithm,
        server_covered={e.edge_config.id for e in edges},  # type: ignore[attr-defined]
    )
    inbox: simpy.Store = simpy.Store(env)

    # Build the OrderedDict[id -> DummyEdge]
    od: OrderedDict[str, DummyEdge] = OrderedDict((e.edge_config.id, e) for e in edges)  # type: ignore[attr-defined]

    lb = LoadBalancerRuntime(
        env=env,
        lb_config=lb_cfg,
        lb_out_edges=cast("OrderedDict[str, EdgeRuntime]", od),
        lb_box=inbox,
    )
    lb.start()
    return lb


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_round_robin_rotation(env: simpy.Environment) -> None:
    """Three requests, two edges ⇒ order must be edge-0, edge-1, edge-0."""
    edge0, edge1 = DummyEdge("srv-A"), DummyEdge("srv-B")
    lb = make_lb_runtime(env, LbAlgorithmsName.ROUND_ROBIN, [edge0, edge1])

    for _ in range(3):
        lb.lb_box.put(DummyState())

    env.run()

    assert len(edge0.received) == 2
    assert len(edge1.received) == 1

    tag = SystemNodes.LOAD_BALANCER.value
    assert edge0.received[0].history[0].startswith(f"{tag}:")
    assert edge0.received[1].history[0].startswith(f"{tag}:")


def test_least_connections_picks_lowest(env: simpy.Environment) -> None:
    """Edge with fewer concurrent connections must be selected."""
    busy = DummyEdge("busy", concurrent=10)
    idle = DummyEdge("idle", concurrent=1)

    lb = make_lb_runtime(env, LbAlgorithmsName.LEAST_CONNECTIONS, [busy, idle])
    lb.lb_box.put(DummyState())

    env.run()

    assert idle.received
    assert not busy.received


def test_no_edges_is_noop(env: simpy.Environment) -> None:
    """
    With an empty mapping of lb_out_edges, starting the LB and running the env
    should be a no-op (no assertions raised).
    """
    lb_cfg = LoadBalancer(
        id="lb-empty",
        algorithms=LbAlgorithmsName.ROUND_ROBIN,
        server_covered=set(),
    )
    lb = LoadBalancerRuntime(
        env=env,
        lb_config=lb_cfg,
        lb_out_edges=cast("OrderedDict[str, EdgeRuntime]", OrderedDict()),
        lb_box=simpy.Store(env),
    )

    lb.start()
    # No events in the env; this should simply return without error.
    env.run()



# --------------------------------------------------------------------------- #
# New FCFS (FIFO tokens) tests                                                #
# --------------------------------------------------------------------------- #

def test_fcfs_immediate_edge_means_zero_wait(env: simpy.Environment) -> None:
    """If an edge is already available, no waiting time is recorded (only >0)."""
    edge = DummyEdge("srv-A")
    lb = make_lb_runtime(env, LbAlgorithmsName.FCFS, [edge])

    # Immediate request: token is already primed, so Wq=0 (not recorded)
    lb.lb_box.put(DummyState())
    env.run()

    assert len(edge.received) == 1
    # LB only records times > 0: no wait ⇒ no entry
    assert list(lb.lb_waiting_times) == [0.0]


def test_fcfs_wait_until_edge_added(env: simpy.Environment) -> None:
    """
    No edge at startup: the request waits until we add an edge,
    then LB measures Wq ≈ Δt.
    """
    lb_cfg = LoadBalancer(
        id="lb-1",
        algorithms=LbAlgorithmsName.FCFS,
        server_covered=set(),
    )
    inbox: simpy.Store = simpy.Store(env)

    # Start with no edges
    od: OrderedDict[str, EdgeRuntime] = cast(
        "OrderedDict[str, EdgeRuntime]",
        OrderedDict(),  # initially empty
    )

    lb = LoadBalancerRuntime(
        env=env,
        lb_config=lb_cfg,
        lb_out_edges=od,
        lb_box=inbox,
    )
    lb.start()

    # One request arrives at t=0
    inbox.put(DummyState())

    # After 5s we add an edge and notify LB
    edge = DummyEdge("srv-A")

    def add_edge_after_5s() -> TypingGenerator[simpy.events.Event, None, None]:
        yield env.timeout(5.0)
        lb.lb_out_edges["srv-A"] = cast("EdgeRuntime", edge)
        lb.on_edge_added("srv-A")

    env.process(add_edge_after_5s())
    env.run()

    assert len(edge.received) == 1
    waits = list(lb.lb_waiting_times)
    assert len(waits) == 1
    assert math.isclose(waits[0], 5.0, rel_tol=1e-6, abs_tol=1e-6)


def test_fcfs_stale_token_is_discarded(env: simpy.Environment) -> None:
    """
    If a token exists but the edge is removed before a request arrives,
    that token becomes stale and must be discarded. The request waits until
    a valid edge is re-added and notified.
    """
    # Start with one edge (it will be removed, leaving a stale token in the FIFO)
    first_edge = DummyEdge("srv-old")
    lb = make_lb_runtime(env, LbAlgorithmsName.FCFS, [first_edge])

    # Remove the edge before the request arrives (stale token left behind)
    lb.lb_out_edges.pop("srv-old", None)

    # Request arrives at t=0 → consumes stale token (discarded)
    lb.lb_box.put(DummyState())

    # At t=7s add a new edge and notify LB
    new_edge = DummyEdge("srv-new")

    def readd_after_7s() -> TypingGenerator[simpy.events.Event, None, None]:
        yield env.timeout(7.0)
        lb.lb_out_edges["srv-new"] = cast("EdgeRuntime", new_edge)
        lb.on_edge_added("srv-new")

    env.process(readd_after_7s())
    env.run()

    assert len(new_edge.received) == 1
    waits = list(lb.lb_waiting_times)
    assert len(waits) == 1
    # The waiting time should be ~7s
    assert math.isclose(waits[0], 7.0, rel_tol=1e-6, abs_tol=1e-6)


def test_fcfs_fifo_order_preserved(env: simpy.Environment) -> None:
    """
    With two initial edges, two requests must use the tokens in the
    same order as insertion (FIFO).
    """
    e0 = DummyEdge("srv-0")
    e1 = DummyEdge("srv-1")
    # OrderedDict in make_lb_runtime preserves order: srv-0, then srv-1
    lb = make_lb_runtime(env, LbAlgorithmsName.FCFS, [e0, e1])

    lb.lb_box.put(DummyState())
    lb.lb_box.put(DummyState())
    env.run()

    # First request → first edge, second request → second edge
    assert len(e0.received) == 1
    assert len(e1.received) == 1
