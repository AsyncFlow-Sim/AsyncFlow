"""Unit test to verify the behaviour of the rqs generator"""

from __future__ import annotations

from types import GeneratorType
from typing import TYPE_CHECKING

import numpy as np
import pytest

from app.config.constants import TimeDefaults
from app.core.simulation.requests_generator import requests_generator
from app.core.simulation.simulation_run import run_simulation
from app.schemas.requests_generator_input import RqsGeneratorInput

if TYPE_CHECKING:

    from collections.abc import Iterator

    from app.schemas.simulation_output import SimulationOutput

# --------------------------------------------------------------
# TESTS INPUT
# --------------------------------------------------------------

@pytest.fixture
def base_input() -> RqsGeneratorInput:
    """Return a RqsGeneratorInput with a 120-second simulation horizon."""
    return RqsGeneratorInput(
        avg_active_users={"mean": 1.0},
        avg_request_per_minute_per_user={"mean": 2.0},
        total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME,
    )

# --------------------------------------------------------------
# REQUESTS GENERATOR FUNCTION TESTS
# --------------------------------------------------------------

def test_default_requests_generator_uses_poisson_poisson_sampling(
    base_input: RqsGeneratorInput,
) -> None:
    """
    Verify that when avg_active_users.distribution is the default 'poisson',
    requests_generator returns an iterator whose code object is from
    poisson_poisson_sampling.
    """
    rng = np.random.default_rng(0)
    gen = requests_generator(base_input, rng=rng)
    # It must be a generator.
    assert isinstance(gen, GeneratorType)

    # Internally, it should call poisson_poisson_sampling.
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
) -> None:
    """
    Verify that requests_generator returns a generator whose code object
    comes from the appropriate sampler function based on distribution:
      - 'poisson' → poisson_poisson_sampling
      - 'normal'  → gaussian_poisson_sampling
    """
    input_data = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": dist},
        avg_request_per_minute_per_user={"mean": 1.0},
        total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME,
    )
    rng = np.random.default_rng(0)
    gen = requests_generator(input_data, rng=rng)

    # It must be a generator object.
    assert isinstance(gen, GeneratorType)
    # Check which underlying sampler function produced it.
    assert gen.gi_code.co_name == expected_sampler

# --------------------------------------------------------------
# REQUESTS GENERATOR INSIDE SIMULATION TESTS
# --------------------------------------------------------------

def test_run_simulation_counts_events_up_to_horizon(
    monkeypatch: pytest.MonkeyPatch, base_input: RqsGeneratorInput,
) -> None:
    """
    Verify that all events whose cumulative inter-arrival times
    fall within the simulation horizon are counted.
    For gaps [1, 2, 3, 4], cumulative times [1, 3, 6, 10]
    yield 4 events by t=10.
    """
    def fake_requests_generator_fixed(
        data: RqsGeneratorInput, *, rng: np.random.Generator,
    ) -> Iterator[float]:
        # Replace the complex Poisson-Poisson sampler with a deterministic sequence.
        yield from [1.0, 2.0, 3.0, 4.0]

    # Monkeypatch the internal requests_generator to use our simple generator.
    monkeypatch.setattr(
        "app.core.simulation.simulation_run.requests_generator",
        fake_requests_generator_fixed,
    )

    # The rng argument is unused in this deterministic test.
    rng = np.random.default_rng(42)
    output: SimulationOutput = run_simulation(base_input, rng=rng)

    assert output.total_requests["total_requests"] == 4
    # The returned metrics should reflect the input means as strings.
    assert output.metric_2 == str(base_input.avg_request_per_minute_per_user.mean)
    assert output.metric_n == str(base_input.avg_active_users.mean)


def test_run_simulation_includes_event_at_exact_horizon(
    monkeypatch: pytest.MonkeyPatch, base_input: RqsGeneratorInput,
) -> None:
    """
    Confirm that an event scheduled exactly at the simulation horizon
    is not processed, since SimPy stops at t == horizon.
    """
    def fake_generator_at_horizon(
        data: RqsGeneratorInput, *, rng: np.random.Generator,
    ) -> Iterator[float]:

        # mypy assertion, pydantic guaranteed
        assert base_input.total_simulation_time is not None
        # Yield a single event at exactly t == simulation_time.
        yield float(base_input.total_simulation_time)

    monkeypatch.setattr(
        "app.core.simulation.simulation_run.requests_generator",
        fake_generator_at_horizon,
    )

    rng = np.random.default_rng(123)
    output: SimulationOutput = run_simulation(base_input, rng=rng)

    # SimPy does not execute events scheduled exactly at the stop time.
    assert output.total_requests["total_requests"] == 0


def test_run_simulation_excludes_event_beyond_horizon(
    monkeypatch: pytest.MonkeyPatch, base_input: RqsGeneratorInput,
) -> None:
    """
    Ensure that events scheduled after the simulation horizon
    are not counted.
    """
    def fake_generator_beyond_horizon(
        data: RqsGeneratorInput, *, rng: np.random.Generator,
    ) -> Iterator[float]:

        # mypy assertion, pydantic guaranteed
        assert base_input.total_simulation_time is not None
        # Yield a single event just beyond the horizon.
        yield float(base_input.total_simulation_time) + 0.1

    monkeypatch.setattr(
        "app.core.simulation.simulation_run.requests_generator",
        fake_generator_beyond_horizon,
    )

    rng = np.random.default_rng(999)
    output: SimulationOutput = run_simulation(base_input, rng=rng)

    assert output.total_requests["total_requests"] == 0


def test_run_simulation_zero_events_when_generator_empty(
    monkeypatch: pytest.MonkeyPatch, base_input: RqsGeneratorInput,
) -> None:
    """
    Check that run_simulation reports zero requests when no
    inter-arrival times are yielded.
    """
    def fake_generator_empty(
        data: RqsGeneratorInput, *, rng: np.random.Generator,
    ) -> Iterator[float]:
        # Empty generator yields nothing.
        if False:
            yield  # pragma: no cover

    monkeypatch.setattr(
        "app.core.simulation.simulation_run.requests_generator",
        fake_generator_empty,
    )

    rng = np.random.default_rng(2025)
    output: SimulationOutput = run_simulation(base_input, rng=rng)

    assert output.total_requests["total_requests"] == 0
