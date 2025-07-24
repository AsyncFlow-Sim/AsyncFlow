"""Unit-tests for :class:`EdgeRuntime` (delivery / drop paths)."""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import simpy

from app.config.constants import SystemEdges, SystemNodes
from app.runtime.actors.edge import EdgeRuntime
from app.runtime.rqs_state import RequestState
from app.schemas.random_variables_config import RVConfig
from app.schemas.system_topology.full_system_topology import Edge

if TYPE_CHECKING:

    import numpy as np

# --------------------------------------------------------------------------- #
# Dummy RNG                                                                   #
# --------------------------------------------------------------------------- #


class DummyRNG:
    """Return preset values for ``uniform`` and ``normal``."""

    def __init__(self, *, uniform_value: float, normal_value: float = 0.0) -> None:
        """Attribute init"""
        self.uniform_value = uniform_value
        self.normal_value = normal_value
        self.uniform_called = False
        self.normal_called = False


    def uniform(self) -> float:
        """Intercept ``rng.uniform`` calls."""
        self.uniform_called = True
        return self.uniform_value

    def normal(self, _mean: float, _sigma: float) -> float:
        """Intercept ``rng.normal`` calls."""
        self.normal_called = True
        return self.normal_value


# --------------------------------------------------------------------------- #
# Helper to build an EdgeRuntime                                              #
# --------------------------------------------------------------------------- #


def _make_edge(
    env: simpy.Environment,
    *,
    uniform_value: float,
    normal_value: float = 0.0,
    dropout_rate: float = 0.0,
) -> tuple[EdgeRuntime, DummyRNG, simpy.Store]:
    """Attributes init"""
    rng = DummyRNG(uniform_value=uniform_value, normal_value=normal_value)

    store: simpy.Store = simpy.Store(env)
    edge_cfg = Edge(
        id="edge-1",
        source="src",
        target="dst",
        latency=RVConfig(mean=0.0, variance=1.0, distribution="normal"),
        dropout_rate=dropout_rate,
    )

    edge_rt = EdgeRuntime(
        env=env,
        edge_config=edge_cfg,
        rng=cast("np.random.Generator", rng),
        target_box=store,
    )
    return edge_rt, rng, store


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_edge_delivers_message_when_not_dropped() -> None:
    """A message traverses the edge and calls the latency sampler once."""
    env = simpy.Environment()
    edge_rt, rng, store = _make_edge(
        env,
        uniform_value=0.9,
        normal_value=0.5,
        dropout_rate=0.2,
    )

    state = RequestState(id=1, initial_time=0.0)
    state.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)

    edge_rt.transport(state)
    env.run()

    assert len(store.items) == 1
    delivered: RequestState = store.items[0]
    last = delivered.history[-1]
    assert last.component_type is SystemEdges.NETWORK_CONNECTION
    assert last.component_id == "edge-1"
    assert rng.uniform_called is True
    assert rng.normal_called is True


def test_edge_drops_message_when_uniform_below_threshold() -> None:
    """A message is dropped when the random draw is below *dropout_rate*."""
    env = simpy.Environment()
    edge_rt, rng, store = _make_edge(
        env,
        uniform_value=0.1,  # < dropout → drop
        dropout_rate=0.5,
    )

    state = RequestState(id=1, initial_time=0.0)
    state.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)

    edge_rt.transport(state)
    env.run()

    assert len(store.items) == 0
    last = state.history[-1]
    assert last.component_id.endswith("dropped")
    assert rng.uniform_called is True
    assert rng.normal_called is False
