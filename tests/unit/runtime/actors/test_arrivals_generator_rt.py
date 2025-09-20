"""Unit tests for :class:`ArrivalsGeneratorRuntime` with the new arrivals API."""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import numpy as np
import pytest
import simpy

from asyncflow.runtime.actors.arrivals_generator import ArrivalsGeneratorRuntime

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from numpy.random import Generator as NpGenerator

    from asyncflow.runtime.actors.edge import EdgeRuntime
    from asyncflow.runtime.rqs_state import RequestState
    from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
    from asyncflow.schemas.settings.simulation import SimulationSettings


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
class _DummyEdgeRuntime:
    """Minimal stub capturing transported :class:`RequestState`."""

    def __init__(self) -> None:
        self.received: list[RequestState] = []

    def transport(self, state: RequestState) -> None:
        """Collect every state passed through the edge."""
        self.received.append(state)


def _make_runtime(  # noqa: PLR0913
    env: simpy.Environment,
    edge: _DummyEdgeRuntime,
    arrivals: ArrivalsGenerator,
    sim_settings: SimulationSettings,
    arrivals_generator_box: simpy.Store | None = None,
    completed_box: simpy.Store | None = None,
    *,
    seed: int = 0,
) -> ArrivalsGeneratorRuntime:
    """Factory returning a fully wired :class:`ArrivalsGeneratorRuntime`."""
    rng: NpGenerator = np.random.default_rng(seed)


    if arrivals_generator_box is None:
        arrivals_generator_box = simpy.Store(env)
    if completed_box is None:
        completed_box = simpy.Store(env)

    return ArrivalsGeneratorRuntime(
        env=env,
        out_edge=cast("EdgeRuntime", edge),
        arrivals=arrivals,
        sim_settings=sim_settings,
        rng=rng,
        arrivals_generator_box=arrivals_generator_box,
        completed_box=completed_box,
    )


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #
def test_event_arrival_generates_expected_number_of_requests(
    monkeypatch: pytest.MonkeyPatch,
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """Given deterministic gaps, exactly that many requests are sent."""
    gaps = [1.0, 2.0, 3.0]
    called = {"count": 0}

    def _fake_general_interarrivals(**_: object) -> Iterator[float]:
        called["count"] += 1
        yield from gaps

    # Patch the *bound* symbol used inside the runtime module.
    monkeypatch.setattr(
        "asyncflow.runtime.actors.arrivals_generator.general_interarrivals",
        _fake_general_interarrivals,
        raising=True,
    )

    env = simpy.Environment()
    edge = _DummyEdgeRuntime()
    runtime = _make_runtime(env, edge, arrivals_gen, sim_settings)

    env.process(runtime._event_arrival())  # noqa: SLF001
    env.run(until=sum(gaps) + 0.1)

    # Sampler called once and exactly len(gaps) states delivered.
    assert called["count"] == 1
    assert len(edge.received) == len(gaps)

    # IDs are 1..n, and initial_time equals cumulative gaps (exact in SimPy).
    cumul = 0.0
    for i, st in enumerate(edge.received, start=1):
        cumul += gaps[i - 1]
        assert st.id == i
        assert st.initial_time == pytest.approx(cumul, rel=0, abs=1e-12)


def test_start_returns_process_and_runs(
    monkeypatch: pytest.MonkeyPatch,
    arrivals_gen: ArrivalsGenerator,
    sim_settings: SimulationSettings,
) -> None:
    """`start()` returns a SimPy process and triggers transports."""
    gaps = [0.05]

    def _fake_general_interarrivals(**_: object) -> Iterator[float]:
        yield from gaps

    monkeypatch.setattr(
        "asyncflow.runtime.actors.arrivals_generator.general_interarrivals",
        _fake_general_interarrivals,
        raising=True,
    )

    env = simpy.Environment()
    edge = _DummyEdgeRuntime()
    runtime = _make_runtime(env, edge, arrivals_gen, sim_settings)

    proc = runtime.start()
    assert isinstance(proc, simpy.events.Process)

    env.run(until=sum(gaps) + 0.01)
    assert len(edge.received) == 1
