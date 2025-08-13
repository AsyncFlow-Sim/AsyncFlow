"""Unit-tests for `gaussian_poisson_sampling`."""

from __future__ import annotations

import itertools
from types import GeneratorType
from typing import TYPE_CHECKING

import pytest
from numpy.random import Generator, default_rng

from asyncflow.config.constants import TimeDefaults
from asyncflow.samplers.gaussian_poisson import (
    gaussian_poisson_sampling,
)
from asyncflow.schemas.random_variables_config import RVConfig
from asyncflow.schemas.rqs_generator_input import RqsGeneratorInput

if TYPE_CHECKING:

    from asyncflow.schemas.simulation_settings_input import SimulationSettings

# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------


@pytest.fixture
def rqs_cfg() -> RqsGeneratorInput:
    """Minimal, valid RqsGeneratorInput for Gaussian-Poisson tests."""
    return RqsGeneratorInput(
        id= "gen-1",
        avg_active_users=RVConfig(
            mean=10.0,
            variance=4.0,
            distribution="normal",
        ),
        avg_request_per_minute_per_user=RVConfig(mean=30.0),
        user_sampling_window=TimeDefaults.USER_SAMPLING_WINDOW,
    )



# ---------------------------------------------------------------------------
# BASIC BEHAVIOUR
# ---------------------------------------------------------------------------


def test_returns_generator_type(
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
    rng: Generator,
) -> None:
    """The function must return a generator object."""
    gen = gaussian_poisson_sampling(rqs_cfg, sim_settings, rng=rng)
    assert isinstance(gen, GeneratorType)


def test_generates_positive_gaps(
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """
    With nominal parameters the sampler should emit at least a few positive
    gaps, and the cumulative time must stay below the horizon.
    """
    gaps: list[float] = list(
        itertools.islice(
            gaussian_poisson_sampling(rqs_cfg, sim_settings, rng=default_rng(42)),
            1000,
        ),
    )

    assert gaps, "Expected at least one event"
    assert all(g > 0.0 for g in gaps), "No gap may be ≤ 0"
    assert sum(gaps) < sim_settings.total_simulation_time


# ---------------------------------------------------------------------------
# EDGE CASE: ZERO USERS
# ---------------------------------------------------------------------------


def test_zero_users_produces_no_events(
    monkeypatch: pytest.MonkeyPatch,
    rqs_cfg: RqsGeneratorInput,
    sim_settings: SimulationSettings,
) -> None:
    """
    If every Gaussian draw returns 0 users, Λ == 0 and the generator must
    yield no events at all.
    """

    def fake_truncated_gaussian(
        mean: float,
        var: float,
        rng: Generator,
    ) -> float:
        return 0.0  # force U = 0

    monkeypatch.setattr(
        "asyncflow.samplers.gaussian_poisson.truncated_gaussian_generator",
        fake_truncated_gaussian,
    )

    gaps: list[float] = list(
        gaussian_poisson_sampling(rqs_cfg, sim_settings, rng=default_rng(123)),
    )

    assert gaps == []  # no events should be generated
