"""Validation tests for RVConfig, RqsGenerator and SimulationSettings."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from asyncflow.config.constants import Distribution, TimeDefaults
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.workload.generator import RqsGenerator

# --------------------------------------------------------------------------- #
# RVCONFIG                                                                    #
# --------------------------------------------------------------------------- #


def test_normal_sets_variance_to_mean() -> None:
    """If variance is omitted for 'normal', it defaults to mean."""
    cfg = RVConfig(mean=10, distribution=Distribution.NORMAL)
    assert cfg.variance == 10.0


def test_log_normal_sets_variance_to_mean() -> None:
    """If variance is omitted for 'log_normal', it defaults to mean."""
    cfg = RVConfig(mean=5, distribution=Distribution.LOG_NORMAL)
    assert cfg.variance == 5.0


def test_poisson_keeps_variance_none() -> None:
    """If variance is omitted for 'poisson', it remains None."""
    cfg = RVConfig(mean=5, distribution=Distribution.POISSON)
    assert cfg.variance is None


def test_uniform_keeps_variance_none() -> None:
    """If variance is omitted for 'uniform', it remains None."""
    cfg = RVConfig(mean=1, distribution=Distribution.UNIFORM)
    assert cfg.variance is None


def test_exponential_keeps_variance_none() -> None:
    """If variance is omitted for 'exponential', it remains None."""
    cfg = RVConfig(mean=2.5, distribution=Distribution.EXPONENTIAL)
    assert cfg.variance is None


def test_explicit_variance_is_preserved() -> None:
    """An explicit variance value is not modified."""
    cfg = RVConfig(mean=8, distribution=Distribution.NORMAL, variance=4)
    assert cfg.variance == 4.0


def test_mean_must_be_numeric() -> None:
    """A non-numeric mean triggers a ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig(mean="not a number", distribution=Distribution.POISSON)


def test_missing_mean_field() -> None:
    """Omitting mean raises a 'field required' ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig.model_validate({"distribution": Distribution.NORMAL})


def test_default_distribution_is_poisson() -> None:
    """If distribution is missing, it defaults to 'poisson'."""
    cfg = RVConfig(mean=3.3)
    assert cfg.distribution == Distribution.POISSON
    assert cfg.variance is None


def test_explicit_variance_kept_for_poisson() -> None:
    """Variance is kept even when distribution is poisson."""
    cfg = RVConfig(mean=4.0, distribution=Distribution.POISSON, variance=2.2)
    assert cfg.variance == pytest.approx(2.2)


def test_invalid_distribution_literal_raises() -> None:
    """An unsupported distribution literal raises ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig(mean=5.0, distribution="not_a_dist")


# --------------------------------------------------------------------------- #
# RqsGenerator - USER_SAMPLING_WINDOW & DISTRIBUTION CONSTRAINTS         #
# --------------------------------------------------------------------------- #


def _valid_poisson_cfg(mean: float = 1.0) -> dict[str, float | str]:
    """Helper: minimal Poisson config for JSON-style input."""
    return {"mean": mean, "distribution": Distribution.POISSON}


def _valid_normal_cfg(mean: float = 1.0) -> dict[str, float | str]:
    """Helper: minimal Normal config for JSON-style input."""
    return {"mean": mean, "distribution": Distribution.NORMAL}


def test_default_user_sampling_window() -> None:
    """If user_sampling_window is missing it defaults to the constant."""
    inp = RqsGenerator(
        id="rqs-1",
        avg_active_users=_valid_poisson_cfg(),
        avg_request_per_minute_per_user=_valid_poisson_cfg(),
    )
    assert inp.user_sampling_window == TimeDefaults.USER_SAMPLING_WINDOW


def test_explicit_user_sampling_window_kept() -> None:
    """An explicit user_sampling_window is preserved."""
    inp = RqsGenerator(
        id="rqs-1",
        avg_active_users=_valid_poisson_cfg(),
        avg_request_per_minute_per_user=_valid_poisson_cfg(),
        user_sampling_window=30,
    )
    assert inp.user_sampling_window == 30


def test_user_sampling_window_not_int_raises() -> None:
    """A non-integer user_sampling_window raises ValidationError."""
    with pytest.raises(ValidationError):
        RqsGenerator(
            id="rqs-1",
            avg_active_users=_valid_poisson_cfg(),
            avg_request_per_minute_per_user=_valid_poisson_cfg(),
            user_sampling_window="not-int",
        )


def test_user_sampling_window_above_max_raises() -> None:
    """user_sampling_window above the max constant raises ValidationError."""
    too_large = TimeDefaults.MAX_USER_SAMPLING_WINDOW + 1
    with pytest.raises(ValidationError):
        RqsGenerator(
            id="rqs-1",
            avg_active_users=_valid_poisson_cfg(),
            avg_request_per_minute_per_user=_valid_poisson_cfg(),
            user_sampling_window=too_large,
        )


def test_avg_request_must_be_poisson() -> None:
    """avg_request_per_minute_per_user must be Poisson; Normal raises."""
    with pytest.raises(ValidationError):
        RqsGenerator(
            id="rqs-1",
            avg_active_users=_valid_poisson_cfg(),
            avg_request_per_minute_per_user=_valid_normal_cfg(),
        )


def test_avg_active_users_invalid_distribution_raises() -> None:
    """avg_active_users cannot be Exponential; only Poisson or Normal allowed."""
    bad_cfg = {"mean": 1.0, "distribution": Distribution.EXPONENTIAL}
    with pytest.raises(ValidationError):
        RqsGenerator(
            id="rqs-1",
            avg_active_users=bad_cfg,
            avg_request_per_minute_per_user=_valid_poisson_cfg(),
        )


def test_valid_poisson_poisson_configuration() -> None:
    """Poisson-Poisson combo is accepted."""
    cfg = RqsGenerator(
        id="rqs-1",
        avg_active_users=_valid_poisson_cfg(),
        avg_request_per_minute_per_user=_valid_poisson_cfg(),
    )
    assert cfg.avg_active_users.distribution is Distribution.POISSON
    assert (
        cfg.avg_request_per_minute_per_user.distribution
        is Distribution.POISSON
    )


def test_valid_normal_poisson_configuration() -> None:
    """Normal-Poisson combo is accepted."""
    cfg = RqsGenerator(
        id="rqs-1",
        avg_active_users=_valid_normal_cfg(),
        avg_request_per_minute_per_user=_valid_poisson_cfg(),
    )
    assert cfg.avg_active_users.distribution is Distribution.NORMAL
    assert (
        cfg.avg_request_per_minute_per_user.distribution
        is Distribution.POISSON
    )


# --------------------------------------------------------------------------- #
# SIMULATIONSETTINGS - TOTAL_SIMULATION_TIME                                  #
# --------------------------------------------------------------------------- #


def test_default_total_simulation_time() -> None:
    """If total_simulation_time is missing it defaults to the constant."""
    settings = SimulationSettings()
    assert settings.total_simulation_time == TimeDefaults.SIMULATION_TIME


def test_explicit_total_simulation_time_kept() -> None:
    """An explicit total_simulation_time is preserved."""
    settings = SimulationSettings(total_simulation_time=3_000)
    assert settings.total_simulation_time == 3_000


def test_total_simulation_time_not_int_raises() -> None:
    """A non-integer total_simulation_time raises ValidationError."""
    with pytest.raises(ValidationError):
        SimulationSettings(total_simulation_time="three thousand")


def test_total_simulation_time_below_minimum_raises() -> None:
    """A total_simulation_time below the minimum constant raises ValidationError."""
    too_small = TimeDefaults.MIN_SIMULATION_TIME - 1
    with pytest.raises(ValidationError):
        SimulationSettings(total_simulation_time=too_small)
