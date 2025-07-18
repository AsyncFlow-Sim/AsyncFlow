"""Unit tests for `poisson_poisson_sampling`."""

from __future__ import annotations

import itertools
import math
from types import GeneratorType
from typing import TYPE_CHECKING

import pytest
from numpy.random import Generator, default_rng

from app.config.constants import TimeDefaults
from app.core.event_samplers.poisson_poisson import poisson_poisson_sampling
from app.schemas.random_variables_config import RVConfig
from app.schemas.requests_generator_input import RqsGeneratorInput

if TYPE_CHECKING:

    from app.schemas.simulation_settings_input import SimulationSettings


@pytest.fixture
def rqs_cfg() -> RqsGeneratorInput:
    """Return a minimal, valid RqsGeneratorInput for the sampler tests."""
    return RqsGeneratorInput(
        id="gen-1",
        avg_active_users={"mean": 1.0, "distribution": "poisson"},
        avg_request_per_minute_per_user={"mean": 60.0, "distribution": "poisson"},
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )

# --------------------------------------------------------
# BASIC SHAPE AND TYPE TESTS
# --------------------------------------------------------


def test_sampler_returns_generator(
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    rng: Generator,
) -> None:
    """Function must return a generator object."""
    gen = poisson_poisson_sampling(rqs_cfg, sim_settings, rng=rng)
    assert isinstance(gen, GeneratorType)


def test_all_gaps_are_positive(
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """Every yielded gap must be strictly positive."""
    gaps = list(
        itertools.islice(
            poisson_poisson_sampling(rqs_cfg, sim_settings, rng=default_rng(1)),
            1_000,
        ),
    )
    assert all(g > 0.0 for g in gaps)


# ---------------------------------------------------------------------------
# REPRODUCIBILITY WITH FIXED SEED
# ---------------------------------------------------------------------------


def test_sampler_is_reproducible_with_fixed_seed(
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """Same RNG seed must produce identical first N gaps."""
    seed = 42
    n_samples = 15

    gaps_1 = list(
        itertools.islice(
            poisson_poisson_sampling(rqs_cfg, sim_settings, rng=default_rng(seed)),
            n_samples,
        ),
    )
    gaps_2 = list(
        itertools.islice(
            poisson_poisson_sampling(rqs_cfg, sim_settings, rng=default_rng(seed)),
            n_samples,
        ),
    )
    assert gaps_1 == gaps_2


# ---------------------------------------------------------------------------
# EDGE CASE: ZERO USERS
# ---------------------------------------------------------------------------


def test_zero_users_produces_no_events(
    sim_settings: SimulationSettings,
) -> None:
    """If the mean user count is zero the generator must yield no events."""
    cfg_zero = RqsGeneratorInput(
        id="gen-1",
        avg_active_users=RVConfig(mean=0.0, distribution="poisson"),
        avg_request_per_minute_per_user=RVConfig(mean=60.0, distribution="poisson"),
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )

    gaps: list[float] = list(
        poisson_poisson_sampling(cfg_zero, sim_settings, rng=default_rng(123)),
    )
    assert gaps == []


# ---------------------------------------------------------------------------
# CUMULATIVE TIME NEVER EXCEEDS THE HORIZON
# ---------------------------------------------------------------------------


def test_cumulative_time_never_exceeds_horizon(
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """Sum of gaps must stay below the simulation horizon."""
    gaps: list[float] = list(
        poisson_poisson_sampling(rqs_cfg, sim_settings, rng=default_rng(7)),
    )
    cum_time = math.fsum(gaps)
    assert cum_time < sim_settings.total_simulation_time
