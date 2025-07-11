"""Unit tests for gaussian_poisson_sampling."""

from __future__ import annotations

import itertools
from types import GeneratorType

import numpy as np
import pytest

from app.config.constants import TimeDefaults
from app.core.event_samplers.gaussian_poisson import gaussian_poisson_sampling
from app.schemas.requests_generator_input import RVConfig, SimulationInput

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def base_input() -> SimulationInput:
    """Return a minimal, valid SimulationInput for the Gaussian-Poisson sampler."""
    return SimulationInput(
        avg_active_users=RVConfig(
            mean=10.0, variance=4.0, distribution="normal",
        ),
        avg_request_per_minute_per_user=RVConfig(mean=30.0),
        total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME,
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


def test_returns_generator_type(base_input: SimulationInput) -> None:
    """The function must return a generator object."""
    rng = np.random.default_rng(0)
    gen = gaussian_poisson_sampling(base_input, rng=rng)
    assert isinstance(gen, GeneratorType)


def test_generates_positive_gaps(base_input: SimulationInput) -> None:
    """
    With nominal parameters the sampler should emit at least a few positive
    gaps and no gap must be non-positive.
    """
    rng = np.random.default_rng(42)
    gaps: list[float] = list(
        itertools.islice(gaussian_poisson_sampling(base_input, rng=rng), 1000),
    )

    # At least one event is expected.
    assert gaps
    # No gap may be negative or zero.
    assert all(gap > 0.0 for gap in gaps)
    # The cumulative time of gaps must stay below the horizon.
    assert sum(gaps) < base_input.total_simulation_time


# ---------------------------------------------------------------------------
# Edge-case: zero users ⇒ no events
# ---------------------------------------------------------------------------


def test_zero_users_produces_no_events(
    monkeypatch: pytest.MonkeyPatch,
    base_input: SimulationInput,
) -> None:
    """
    If every Gaussian draw returns 0 users, Λ == 0,
    hence the generator must yield no events at all.
    """

    def fake_truncated_gaussian(
        mean: float,
        var: float,
        rng: np.random.Generator,
    ) -> float:
        return 0.0  # force U = 0

    # Patch the helper so that it always returns 0 users.
    monkeypatch.setattr(
        "app.core.event_samplers.gaussian_poisson.truncated_gaussian_generator",
        fake_truncated_gaussian,
    )

    rng = np.random.default_rng(123)
    gaps = list(gaussian_poisson_sampling(base_input, rng=rng))

    assert gaps == []  # no events should be generated
