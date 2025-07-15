"""Unit-tests for the requests generator and the SimPy runner."""

from __future__ import annotations

from types import GeneratorType
from typing import TYPE_CHECKING

import pytest
from numpy.random import Generator, default_rng

from app.config.constants import TimeDefaults
from app.core.simulation.requests_generator import requests_generator
from app.core.simulation.simulation_run import run_simulation
from app.schemas.full_simulation_input import SimulationPayload
from app.schemas.random_variables_config import RVConfig
from app.schemas.requests_generator_input import RqsGeneratorInput
from app.schemas.simulation_settings_input import SimulationSettings
from app.schemas.system_topology_schema.full_system_topology_schema import (
    TopologyGraph,
    Client,
    TopologyNodes
)

if TYPE_CHECKING:  # Only for static type-checking
    from collections.abc import Iterator

    from app.schemas.simulation_output import SimulationOutput

# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------


@pytest.fixture
def rqs_input() -> RqsGeneratorInput:
    """Minimal RqsGeneratorInput for unit tests."""
    return RqsGeneratorInput(
        avg_active_users=RVConfig(mean=1.0),
        avg_request_per_minute_per_user=RVConfig(mean=2.0),
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )


@pytest.fixture
def settings() -> SimulationSettings:
    """Global simulation settings with a 120-second horizon."""
    return SimulationSettings(total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME)


@pytest.fixture
def topology_minimal() -> TopologyGraph:
    """
    Minimal valid topology:
    - nessun server (lista vuota)
    - un client fittizio con id 'client-1'
    - zero edge
    """
    client = Client(id="client-1")
    nodes = TopologyNodes(servers=[], client=client)
    return TopologyGraph(nodes=nodes, edges=[])


@pytest.fixture
def payload_base(
    rqs_input: RqsGeneratorInput,
    settings: SimulationSettings,
    topology_minimal: TopologyGraph,
) -> SimulationPayload:
    """Complete payload for end-to-end tests."""
    return SimulationPayload(
        rqs_input=rqs_input,
        topology_graph=topology_minimal,
        settings=settings,
    )


@pytest.fixture
def rng() -> Generator:
    """Shared RNG for deterministic tests."""
    return default_rng(0)


# ---------------------------------------------------------------------------
# REQUESTS GENERATOR - FUNCTION-LEVEL
# ---------------------------------------------------------------------------


def test_default_requests_generator_uses_poisson_poisson_sampling(
    rqs_input: RqsGeneratorInput,
    settings: SimulationSettings,
    rng: Generator,
) -> None:
    """Default distribution must map to poisson_poisson_sampling."""
    gen = requests_generator(rqs_input, settings, rng=rng)
    assert isinstance(gen, GeneratorType)
    assert gen.gi_code.co_name == "poisson_poisson_sampling"


@pytest.mark.parametrize(
    ("dist", "expected_sampler"),
    [
        ("poisson", "poisson_poisson_sampling"),
        ("normal", "gaussian_poisson_sampling"),
    ],
)
def test_requests_generator_dispatches_to_correct_sampler(
    dist: str,
    expected_sampler: str,
    rqs_input: RqsGeneratorInput,
    settings: SimulationSettings,
    rng: Generator,
) -> None:
    """Dispatcher must select the sampler that matches *dist*."""
    rqs_input.avg_active_users.distribution = dist  # type: ignore[assignment]
    gen = requests_generator(rqs_input, settings, rng=rng)
    assert isinstance(gen, GeneratorType)
    assert gen.gi_code.co_name == expected_sampler


# ---------------------------------------------------------------------------
# SIMULATION RUNNER
# ---------------------------------------------------------------------------


def _patch_generator(
    monkeypatch: pytest.MonkeyPatch,
    gaps: list[float],
) -> None:
    """Monkey-patch requests_generator with a deterministic gap sequence."""

    def _fake(
        data: RqsGeneratorInput,
        config: SimulationSettings,
        *,
        rng: Generator | None = None,
    ) -> Iterator[float]:
        yield from gaps

    monkeypatch.setattr(
        "app.core.simulation.simulation_run.requests_generator",
        _fake,
    )


def test_run_simulation_counts_events_up_to_horizon(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """All events with cumulative time ≤ horizon must be counted."""
    _patch_generator(monkeypatch, gaps=[1.0, 2.0, 3.0, 4.0])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)

    assert output.total_requests["total_requests"] == 4
    assert output.metric_2 == str(
        payload_base.rqs_input.avg_request_per_minute_per_user.mean,
    )
    assert output.metric_n == str(payload_base.rqs_input.avg_active_users.mean)


def test_run_simulation_skips_event_at_exact_horizon(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """An event scheduled exactly at t == horizon must be ignored."""
    horizon = payload_base.settings.total_simulation_time
    _patch_generator(monkeypatch, gaps=[float(horizon)])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)
    assert output.total_requests["total_requests"] == 0


def test_run_simulation_excludes_event_beyond_horizon(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """Events after the horizon must not be counted."""
    horizon = payload_base.settings.total_simulation_time
    _patch_generator(monkeypatch, gaps=[float(horizon) + 0.1])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)
    assert output.total_requests["total_requests"] == 0


def test_run_simulation_zero_events_when_generator_empty(
    monkeypatch: pytest.MonkeyPatch,
    payload_base: SimulationPayload,
    rng: Generator,
) -> None:
    """run_simulation must return zero requests if the generator is empty."""
    _patch_generator(monkeypatch, gaps=[])

    output: SimulationOutput = run_simulation(payload_base, rng=rng)
    assert output.total_requests["total_requests"] == 0
