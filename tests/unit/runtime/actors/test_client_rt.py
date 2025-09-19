"""Unit-tests for :class:`ClientRuntime` (outbound / inbound paths)."""

from __future__ import annotations

import simpy

from asyncflow.config.enums import SystemEdges, SystemNodes
from asyncflow.runtime.actors.client import ClientRuntime
from asyncflow.runtime.rqs_state import RequestState
from asyncflow.schemas.topology.nodes import Client

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
    edge_rt = DummyEdgeRuntime(env)
    cli_cfg = Client(id="cli-1")

    client = ClientRuntime(
        env=env,
        out_edge=edge_rt,  # type: ignore[arg-type]
        client_box=inbox,
        client_config=cli_cfg,
    )
    client.start()  # start the forwarder
    return inbox, edge_rt


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_outbound_is_forwarded() -> None:
    """First visit ⇒ forwarded; completed store remains empty."""
    env = simpy.Environment()
    inbox, edge_rt = _setup(env)

    req = RequestState(id=1, initial_time=0.0)
    req.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)

    inbox.put(req)
    env.run()

    assert len(edge_rt.forwarded) == 1
    assert req.history[-1].component_type is SystemNodes.CLIENT
    assert req.finish_time is None


