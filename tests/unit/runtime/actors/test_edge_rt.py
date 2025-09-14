"""
Unit tests for :class:`EdgeRuntime`:
* delivery vs. drop paths
* connection-counter bookkeeping
* public properties (`enabled_metrics`, `concurrent_connections`)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import simpy

from asyncflow.config.enums import (
    Distribution,
    SampledMetricName,
    SystemEdges,
    SystemNodes,
)
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.rqs_state import RequestState
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.topology.edges import Edge

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np

    from asyncflow.schemas.settings.simulation import SimulationSettings


# --------------------------------------------------------------------------- #
# Dummy RNG                                                                   #
# --------------------------------------------------------------------------- #
class DummyRNG:
    """Return preset values for ``uniform`` and ``exponential``."""

    def __init__(self, *, uniform_value: float, exp_value: float = 0.0) -> None:
        """Instance for the RNG for tests"""
        self.uniform_value = uniform_value
        self.exp_value = exp_value
        self.uniform_called = False
        self.exp_called = False

    # EdgeRuntime uses .uniform() for drop decision
    def uniform(self) -> float:
        """Uniform rng"""
        self.uniform_called = True
        return self.uniform_value

    # Latency sampler calls .exponential(scale)
    def exponential(self, scale: float) -> float:  # noqa: ARG002
        """Exp rng"""
        self.exp_called = True
        return self.exp_value


# --------------------------------------------------------------------------- #
# Minimal stub for SimulationSettings                                         #
# --------------------------------------------------------------------------- #
class _SettingsStub:
    """Only the attributes required by EdgeRuntime/build_edge_metrics."""

    def __init__(self, enabled_sample_metrics: set[SampledMetricName]) -> None:
        self.enabled_sample_metrics = enabled_sample_metrics
        self.sample_period_s = 0.001  # not used in these unit tests


# --------------------------------------------------------------------------- #
# Helper factory                                                              #
# --------------------------------------------------------------------------- #
def _make_edge(
    env: simpy.Environment,
    *,
    uniform_value: float,
    exp_value: float = 0.0,
    dropout_rate: float = 0.0,
) -> tuple[EdgeRuntime, DummyRNG, simpy.Store]:
    """Create a fully wired :class:`EdgeRuntime` + associated objects."""
    rng = DummyRNG(uniform_value=uniform_value, exp_value=exp_value)
    store: simpy.Store = simpy.Store(env)

    edge_cfg = Edge(
        id="edge-1",
        source="src",
        target="dst",
        latency=RVConfig(mean=1.0, distribution=Distribution.EXPONENTIAL),
        dropout_rate=dropout_rate,
    )

    settings_stub = _SettingsStub(
        enabled_sample_metrics={SampledMetricName.EDGE_CONCURRENT_CONNECTION},
    )

    edge_rt = EdgeRuntime(
        env=env,
        edge_config=edge_cfg,
        rng=cast("np.random.Generator", rng),
        target_box=store,
        settings=cast("SimulationSettings", settings_stub),
    )
    return edge_rt, rng, store


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_edge_delivers_message() -> None:
    """A request traverses the edge when `uniform >= dropout_rate`."""
    env = simpy.Environment()
    edge_rt, rng, store = _make_edge(
        env,
        uniform_value=0.9,
        exp_value=0.5,
        dropout_rate=0.2,
    )

    state = RequestState(id=1, initial_time=0.0)
    state.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)

    assert edge_rt.concurrent_connections == 0

    edge_rt.transport(state)
    env.run()

    # message delivered
    assert len(store.items) == 1
    delivered: RequestState = store.items[0]
    last = delivered.history[-1]
    assert last.component_type is SystemEdges.NETWORK_CONNECTION
    assert last.component_id == "edge-1"

    # RNG calls
    assert rng.uniform_called is True
    assert rng.exp_called is True

    # counter restored
    assert edge_rt.concurrent_connections == 0


def test_edge_drops_message() -> None:
    """A request is dropped when `uniform < dropout_rate`."""
    env = simpy.Environment()
    edge_rt, rng, store = _make_edge(
        env,
        uniform_value=0.1,  # < dropout_rate → drop
        dropout_rate=0.5,
    )

    state = RequestState(id=1, initial_time=0.0)
    state.record_hop(SystemNodes.GENERATOR, "gen-1", env.now)

    edge_rt.transport(state)
    env.run()

    # no delivery
    assert len(store.items) == 0
    last = state.history[-1]
    assert last.component_id.endswith("dropped")

    # RNG calls
    assert rng.uniform_called is True
    assert rng.exp_called is False

    # counter unchanged
    assert edge_rt.concurrent_connections == 0


def test_metric_dict_initialised_and_mutable() -> None:
    """`enabled_metrics` exposes the key and supports list append."""
    env = simpy.Environment()
    edge_rt, _rng, _store = _make_edge(
        env,
        uniform_value=0.9,
        dropout_rate=0.0,
    )

    key = SampledMetricName.EDGE_CONCURRENT_CONNECTION
    assert key in edge_rt.enabled_metrics
    assert edge_rt.enabled_metrics[key] == []

    # Simulate a collector append
    edge_rt.enabled_metrics[key].append(5)
    assert edge_rt.enabled_metrics[key] == [5]
