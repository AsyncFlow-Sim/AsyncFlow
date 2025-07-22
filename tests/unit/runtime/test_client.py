"""Unit-tests for :class:`ClientRuntime` (outbound / inbound paths)."""

from __future__ import annotations

import simpy

from app.config.constants import SystemEdges, SystemNodes
from app.runtime.engine.client import ClientRuntime
from app.runtime.rqs_state import RequestState
from app.schemas.system_topology_schema.full_system_topology_schema import (
    Client,
)

# --------------------------------------------------------------------------- #
# Dummy edge (no real network)                                                #
# --------------------------------------------------------------------------- #


class DummyEdgeRuntime:
    """Collect states passed through *transport* without SimPy side-effects."""

    def __init__(self, env: simpy.Environment) -> None:
        """Init attributes"""
        self.env = env
        self.forwarded: list[RequestState] = []

    # Signature compatible with EdgeRuntime.transport but returns *None*
    def transport(self, state: RequestState) -> None:
        """Transport state"""
        self.forwarded.append(state)


# --------------------------------------------------------------------------- #
# Helper                                                                      #
# --------------------------------------------------------------------------- #


def _setup(
    env: simpy.Environment,
) -> tuple[simpy.Store, simpy.Store, DummyEdgeRuntime]:
    inbox: simpy.Store = simpy.Store(env)
    completed: simpy.Store = simpy.Store(env)
    edge_rt = DummyEdgeRuntime(env)
    cli_cfg = Client(id="cli-1")

    client = ClientRuntime(
        env=env,
        out_edge=edge_rt,  # type: ignore[arg-type]
        client_box=inbox,
        completed_box=completed,
        client_config=cli_cfg,
    )
    client.client_run()  # start the forwarder
    return inbox, completed, edge_rt


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_outbound_is_forwarded() -> None:
    """First visit ⇒ forwarded; completed store remains empty."""
    env = simpy.Environment()
    inbox, completed, edge_rt = _setup(env)

    req = RequestState(id=1, initial_time=0.0)
    req.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)

    inbox.put(req)
    env.run()

    assert len(edge_rt.forwarded) == 1
    assert len(completed.items) == 0
    assert req.history[-1].component_type is SystemNodes.CLIENT
    assert req.finish_time is None


def test_inbound_is_completed() -> None:
    """Second visit ⇒ request stored in *completed_box* and not re-forwarded."""
    env = simpy.Environment()
    inbox, completed, edge_rt = _setup(env)

    req = RequestState(id=2, initial_time=0.0)
    req.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)
    req.record_hop(SystemEdges.NETWORK_CONNECTION, "edge-X", env.now)

    inbox.put(req)
    env.run()

    assert len(edge_rt.forwarded) == 0
    assert len(completed.items) == 1

    done = completed.items[0]
    assert done.finish_time is not None
    assert done.history[-1].component_type is SystemNodes.CLIENT
