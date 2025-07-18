"""Unit-tests for the :class:`RqsGeneratorRuntime` dispatcher and event flow."""
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

import numpy as np
import simpy

from app.config.constants import Distribution
from app.core.runtime.rqs_generator import RqsGeneratorRuntime

if TYPE_CHECKING:

    import pytest
    from numpy.random import Generator

    from app.config.rqs_state import RequestState
    from app.core.runtime.edge import EdgeRuntime
    from app.schemas.requests_generator_input import RqsGeneratorInput
    from app.schemas.simulation_settings_input import SimulationSettings

import importlib

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


class DummyEdgeRuntime:
    """Minimal stub capturing transported :class:`RequestState`."""

    def __init__(self) -> None:
        """Definition of the attributes"""
        self.received: list[RequestState] = []

    def transport(self, state: RequestState) -> None:
        """Collect every state passed through the edge."""
        self.received.append(state)


def _make_runtime(
    env: simpy.Environment,
    edge: DummyEdgeRuntime,
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    *,
    seed: int = 0,
) -> RqsGeneratorRuntime:
    """Factory returning a fully wired :class:`RqsGeneratorRuntime`."""
    rng: Generator = np.random.default_rng(seed)
    return RqsGeneratorRuntime(
        env=env,
        out_edge=cast("EdgeRuntime", edge),
        rqs_generator_data=rqs_input,
        sim_settings=sim_settings,
        rng=rng,
    )


# --------------------------------------------------------------------------- #
# Dispatcher behaviour                                                        #
# --------------------------------------------------------------------------- #


RGR_MODULE = importlib.import_module("app.core.runtime.rqs_generator")

def test_dispatcher_selects_poisson_poisson(
    monkeypatch: pytest.MonkeyPatch,
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """Default (Poisson) distribution must invoke *poisson_poisson_sampling*."""
    called = {"pp": False}

    def _fake_pp(*args: object, **kwargs: object) -> Iterator[float]:
        called["pp"] = True
        return iter(())  # iterator already exhausted

    monkeypatch.setattr(RGR_MODULE, "poisson_poisson_sampling", _fake_pp)

    env = simpy.Environment()
    edge = DummyEdgeRuntime()
    runtime = _make_runtime(env, edge, rqs_input, sim_settings)

    gen = runtime._requests_generator()  # noqa: SLF001
    for _ in gen:
        pass

    assert called["pp"] is True
    assert isinstance(gen, Iterator)


def test_dispatcher_selects_gaussian_poisson(
    monkeypatch: pytest.MonkeyPatch,
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """Normal distribution must invoke *gaussian_poisson_sampling*."""
    rqs_input.avg_active_users.distribution = Distribution.NORMAL
    called = {"gp": False}

    def _fake_gp(*args: object, **kwargs: object) -> Iterator[float]:
        called["gp"] = True
        return iter(())

    monkeypatch.setattr(RGR_MODULE, "gaussian_poisson_sampling", _fake_gp)

    env = simpy.Environment()
    edge = DummyEdgeRuntime()
    runtime = _make_runtime(env, edge, rqs_input, sim_settings)

    gen = runtime._requests_generator()  # noqa: SLF001
    for _ in gen:
        pass

    assert called["gp"] is True
    assert isinstance(gen, Iterator)

# --------------------------------------------------------------------------- #
# Event-arrival flow                                                          #
# --------------------------------------------------------------------------- #


def test_event_arrival_generates_expected_number_of_requests(
    monkeypatch: pytest.MonkeyPatch,
    rqs_input: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """Given a deterministic gap list, exactly that many requests are sent."""
    gaps = [1.0, 2.0, 3.0]

    def _fake_gen(self: object) -> Iterator[float]:
        yield from gaps

    monkeypatch.setattr(
        RqsGeneratorRuntime,
        "_requests_generator",
        _fake_gen,
    )

    env = simpy.Environment()
    edge = DummyEdgeRuntime()
    runtime = _make_runtime(env, edge, rqs_input, sim_settings)

    env.process(runtime._event_arrival()) # noqa: SLF001
    env.run(until=sum(gaps) + 0.1)  # run slightly past the last gap

    assert len(edge.received) == len(gaps)
    ids = [s.id for s in edge.received]
    assert ids == [1, 2, 3]
