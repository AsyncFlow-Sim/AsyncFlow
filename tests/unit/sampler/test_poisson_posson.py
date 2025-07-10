"""Unit tests for the poisson_poisson_sampling generator."""

from __future__ import annotations

import itertools
import math
from types import GeneratorType

import numpy as np
import pytest

from app.config.constants import TimeDefaults
from app.core.event_samplers.poisson_poisson import poisson_poisson_sampling
from app.schemas.simulation_input import RVConfig, SimulationInput


@pytest.fixture
def base_input() -> SimulationInput:
    """Return a minimal-valid SimulationInput for the sampler tests."""
    return SimulationInput(
        # 1 average concurrent user …
        avg_active_users={"mean": 1.0, "distribution": "poisson"},
        # … sending on average 60 req/min → 1 req/s
        avg_request_per_minute_per_user={"mean": 60.0, "distribution": "poisson"},
        total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME,  # 30 min
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,  # 60 s
    )


# ---------------------------------------------------------------------
# BASIC SHAPE / TYPE TESTS
# ---------------------------------------------------------------------


def test_sampler_returns_generator(base_input: SimulationInput) -> None:
    """The function must return a real generator object."""
    rng = np.random.default_rng(0)
    gen = poisson_poisson_sampling(base_input, rng=rng)

    assert isinstance(gen, GeneratorType)


def test_all_gaps_are_positive(base_input: SimulationInput) -> None:
    """Every yielded inter-arrival gap Δt must be > 0."""
    rng = np.random.default_rng(1)
    gaps: list[float] = list(
        itertools.islice(poisson_poisson_sampling(base_input, rng=rng), 1_000),
    )

    # None of the first 1 000 gaps (if any) can be negative or zero
    assert all(gap > 0.0 for gap in gaps)


# ---------------------------------------------------------------------
# REPRODUCIBILITY WITH FIXED RNG SEED
# ---------------------------------------------------------------------


def test_sampler_is_reproducible_with_fixed_seed(base_input: SimulationInput) -> None:
    """Same seed ⇒ identical first N gaps."""
    seed = 42
    n_samples = 15

    gaps_1 = list(
        itertools.islice(
            poisson_poisson_sampling(
                base_input, rng=np.random.default_rng(seed),
            ),
            n_samples,
        ),
    )
    gaps_2 = list(
        itertools.islice(
            poisson_poisson_sampling(
                base_input, rng=np.random.default_rng(seed),
            ),
            n_samples,
        ),
    )

    assert gaps_1 == gaps_2


# ---------------------------------------------------------------------
# EDGE-CASE: ZERO USERS ⇒ NO EVENTS
# ---------------------------------------------------------------------


def test_zero_users_produces_no_events(base_input: SimulationInput) -> None:
    """
    With mean concurrent users == 0 the Poisson draw is almost surely 0,
    so Λ = 0 and the generator should yield no events.
    """
    input_data = SimulationInput(
        avg_active_users=RVConfig(mean=0.0, distribution="poisson"),
        avg_request_per_minute_per_user=RVConfig(mean=60.0, distribution="poisson"),
        total_simulation_time=TimeDefaults.MIN_SIMULATION_TIME,
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )

    rng = np.random.default_rng(123)
    gaps = list(poisson_poisson_sampling(input_data, rng=rng))

    assert gaps == []  # no events expected

# ---------------------------------------------------------------------
# CUMULATIVE TIME ALWAYS < SIMULATION HORIZON
# ---------------------------------------------------------------------


def test_cumulative_time_never_exceeds_horizon(base_input: SimulationInput) -> None:
    """ΣΔt (virtual clock) must stay strictly below total_simulation_time."""
    rng = np.random.default_rng(7)
    gaps = list(poisson_poisson_sampling(base_input, rng=rng))

    cum_time = math.fsum(gaps)
    # Even if the virtual clock can jump when λ == 0,
    # the summed gaps must never exceed the horizon.
    assert cum_time < base_input.total_simulation_time
