"""Unit tests for ``LoadBalancerRuntime`` (round-robin & least-connections)."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, cast

import simpy

from asyncflow.config.constants import LbAlgorithmsName, SystemNodes
from asyncflow.runtime.actors.load_balancer import LoadBalancerRuntime
from asyncflow.schemas.topology.nodes import LoadBalancer

if TYPE_CHECKING:
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
