"""Validation tests for RVConfig, RqsGeneratorInput and SimulationSettings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.constants import Distribution, TimeDefaults
from app.schemas.random_variables_config import RVConfig
from app.schemas.requests_generator_input import RqsGeneratorInput
from app.schemas.simulation_settings_input import SimulationSettings

# ---------------------------------------------------------------------------
# RVCONFIG
# ---------------------------------------------------------------------------


def test_normal_sets_variance_to_mean() -> None:
    """If variance is omitted with 'normal', it defaults to mean."""
    cfg = RVConfig(mean=10, distribution=Distribution.NORMAL)
    assert cfg.variance == 10.0


def test_poisson_keeps_variance_none() -> None:
    """If variance is omitted with 'poisson', it remains None."""
    cfg = RVConfig(mean=5, distribution=Distribution.POISSON)
    assert cfg.variance is None


def test_explicit_variance_is_preserved() -> None:
    """An explicit variance value is not modified."""
    cfg = RVConfig(mean=8, distribution=Distribution.NORMAL, variance=4)
    assert cfg.variance == 4.0


def test_mean_must_be_numeric() -> None:
    """A non numeric mean triggers a ValidationError."""
    with pytest.raises(ValidationError) as exc:
        RVConfig(mean="not a number", distribution=Distribution.POISSON)

    assert any(err["loc"] == ("mean",) for err in exc.value.errors())


def test_missing_mean_field() -> None:
    """Omitting mean raises a 'field required' ValidationError."""
    with pytest.raises(ValidationError) as exc:
        RVConfig.model_validate({"distribution": Distribution.NORMAL})

    assert any(
        err["loc"] == ("mean",) and err["type"] == "missing"
        for err in exc.value.errors()
    )


def test_default_distribution_is_poisson() -> None:
    """If distribution is missing, it defaults to 'poisson'."""
    cfg = RVConfig(mean=3.3)
    assert cfg.distribution == Distribution.POISSON
    assert cfg.variance is None


def test_explicit_variance_kept_for_poisson() -> None:
    """Variance is kept even when distribution is poisson."""
    cfg = RVConfig(mean=4.0, distribution=Distribution.POISSON, variance=2.2)
    assert cfg.variance == pytest.approx(2.2)


def test_invalid_distribution_raises() -> None:
    """An unsupported distribution literal raises ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig(mean=5.0, distribution="not_a_dist")

# ---------------------------------------------------------------------------
# RQSGENERATORINPUT - USER_SAMPLING_WINDOW
# ---------------------------------------------------------------------------


def test_default_user_sampling_window() -> None:
    """If user_sampling_window is missing it defaults to the constant."""
    inp = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
        avg_request_per_minute_per_user={
            "mean": 1.0,
            "distribution": Distribution.POISSON,
        },
    )
    assert inp.user_sampling_window == TimeDefaults.USER_SAMPLING_WINDOW


def test_explicit_user_sampling_window_kept() -> None:
    """An explicit user_sampling_window is preserved."""
    inp = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
        avg_request_per_minute_per_user={
            "mean": 1.0,
            "distribution": Distribution.POISSON,
        },
        user_sampling_window=30,
    )
    assert inp.user_sampling_window == 30


def test_user_sampling_window_not_int_raises() -> None:
    """A non integer user_sampling_window raises ValidationError."""
    with pytest.raises(ValidationError):
        RqsGeneratorInput(
            avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
            avg_request_per_minute_per_user={
                "mean": 1.0,
                "distribution": Distribution.POISSON,
            },
            user_sampling_window="not-int",
        )


def test_user_sampling_window_above_max_raises() -> None:
    """user_sampling_window above the max constant raises ValidationError."""
    too_large = TimeDefaults.MAX_USER_SAMPLING_WINDOW + 1
    with pytest.raises(ValidationError):
        RqsGeneratorInput(
            avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
            avg_request_per_minute_per_user={
                "mean": 1.0,
                "distribution": Distribution.POISSON,
            },
            user_sampling_window=too_large,
        )



# ---------------------------------------------------------------------------
# SIMULATIONSETTINGS - TOTAL_SIMULATION_TIME
# ---------------------------------------------------------------------------


def test_default_total_simulation_time() -> None:
    """If total_simulation_time is missing it defaults to the constant."""
    settings = SimulationSettings()
    assert settings.total_simulation_time == TimeDefaults.SIMULATION_TIME


def test_explicit_total_simulation_time_kept() -> None:
    """An explicit total_simulation_time is preserved."""
    settings = SimulationSettings(total_simulation_time=3_000)
    assert settings.total_simulation_time == 3_000


def test_total_simulation_time_not_int_raises() -> None:
    """A non integer total_simulation_time raises ValidationError."""
    with pytest.raises(ValidationError):
        SimulationSettings(total_simulation_time="three thousand")


def test_total_simulation_time_below_minimum_raises() -> None:
    """A total_simulation_time below the minimum constant raises ValidationError."""
    too_small = TimeDefaults.MIN_SIMULATION_TIME - 1
    with pytest.raises(ValidationError):
        SimulationSettings(total_simulation_time=too_small)
