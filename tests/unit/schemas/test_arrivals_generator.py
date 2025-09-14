"""Validation tests for RVConfig, ArrivalsGenerator and SimulationSettings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asyncflow.config.enums import (
    Distribution,
    SystemNodes,
    TimeDefaults,
    VariabilityLevel,
)
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.settings.simulation import SimulationSettings

# ──────────────────────────────────────────────────────────────────────────────
# RVCONFIG
# ──────────────────────────────────────────────────────────────────────────────


def test_log_normal_sets_variance_to_mean() -> None:
    """If variance is omitted for log-normal, it defaults to the mean."""
    cfg = RVConfig(mean=5.0, distribution=Distribution.LOG_NORMAL)
    assert cfg.variance == pytest.approx(5.0)


def test_poisson_keeps_variance_none() -> None:
    """If variance is omitted for Poisson, it remains None."""
    cfg = RVConfig(mean=5.0, distribution=Distribution.POISSON)
    assert cfg.variance is None


def test_uniform_keeps_variance_none() -> None:
    """If variance is omitted for Uniform, it remains None."""
    cfg = RVConfig(mean=1.0, distribution=Distribution.UNIFORM)
    assert cfg.variance is None


def test_exponential_keeps_variance_none() -> None:
    """If variance is omitted for Exponential, it remains None."""
    cfg = RVConfig(mean=2.5, distribution=Distribution.EXPONENTIAL)
    assert cfg.variance is None


def test_explicit_variance_is_preserved() -> None:
    """An explicit variance value is not modified."""
    cfg = RVConfig(
        mean=8.0,
        distribution=Distribution.LOG_NORMAL,
        variance=4.0,
    )
    assert cfg.variance == pytest.approx(4.0)


def test_mean_must_be_numeric() -> None:
    """A non-numeric mean triggers a ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig(mean="not a number", distribution=Distribution.POISSON)


def test_missing_mean_field() -> None:
    """Omitting mean raises a 'field required' ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig.model_validate({"distribution": Distribution.POISSON})


def test_default_distribution_is_poisson() -> None:
    """If distribution is missing, it defaults to 'poisson'."""
    cfg = RVConfig(mean=3.3)
    assert cfg.distribution is Distribution.POISSON
    assert cfg.variance is None


def test_explicit_variance_kept_for_poisson() -> None:
    """Variance is kept even when distribution is Poisson."""
    cfg = RVConfig(
        mean=4.0,
        distribution=Distribution.POISSON,
        variance=2.2,
    )
    assert cfg.variance == pytest.approx(2.2)


def test_invalid_distribution_literal_raises() -> None:
    """An unsupported distribution literal raises ValidationError."""
    with pytest.raises(ValidationError):
        RVConfig(mean=5.0, distribution="not_a_dist")


# ──────────────────────────────────────────────────────────────────────────────
# ARRIVALSGENERATOR  (new API: lambda_rps, model, variability, empirical_data)
# ──────────────────────────────────────────────────────────────────────────────


def test_type_defaults_to_generator() -> None:
    """`type` defaults to SystemNodes.GENERATOR."""
    ag = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=10.0,
        model=Distribution.POISSON,
    )
    assert ag.type is SystemNodes.GENERATOR


@pytest.mark.parametrize(
    "model",
    [
        Distribution.EXPONENTIAL,
        Distribution.DETERMINISTIC,
        Distribution.POISSON,
        Distribution.UNIFORM,
        # EMPIRICAL is handled by dedicated tests below.
    ],
)
def test_forbids_variability_models_reject_variability(model: Distribution) -> None:
    """Models with intrinsic/non-configurable variability must use variability=None."""
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=5.0,
            model=model,
            variability=VariabilityLevel.LOW,
        )


@pytest.mark.parametrize(
    "model",
    [
        Distribution.LOG_NORMAL,
        Distribution.WEIBULL,
        Distribution.PARETO,
        Distribution.ERLANG,
    ],
)
def test_requires_variability_models_need_variability(model: Distribution) -> None:
    """Models that require a variability level must receive one."""
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=5.0,
            model=model,
        )

    # Now it should pass when variability is provided.
    ag = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=5.0,
        model=model,
        variability=VariabilityLevel.MEDIUM,
    )
    assert ag.variability is VariabilityLevel.MEDIUM


def test_empirical_requires_data() -> None:
    """EMPIRICAL model requires `empirical_data` and forbids variability."""
    # Missing empirical_data → error
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=5.0,
            model=Distribution.EMPIRICAL,
        )

    # Provided empirical_data → OK
    ag = ArrivalsGenerator(
        id="rqs-1",
        lambda_rps=5.0,
        model=Distribution.EMPIRICAL,
        empirical_data=[0.1, 0.3, 0.8],
    )
    assert list(ag.empirical_data or []) == [0.1, 0.3, 0.8]

    # With any non-EMPIRICAL model, empirical_data must be None → error
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=5.0,
            model=Distribution.POISSON,
            empirical_data=[0.1, 0.3],
        )


def test_lambda_rps_must_be_positive() -> None:
    """lambda_rps is PositiveFloat: zero or negative raises."""
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=0.0,
            model=Distribution.POISSON,
        )
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=-1.0,
            model=Distribution.POISSON,
        )


def test_invalid_distribution_literal_at_arrivals_raises() -> None:
    """An invalid distribution literal in ArrivalsGenerator raises."""
    with pytest.raises(ValidationError):
        ArrivalsGenerator(
            id="rqs-1",
            lambda_rps=10.0,
            model="not_a_dist",
        )


# ──────────────────────────────────────────────────────────────────────────────
# SIMULATIONSETTINGS  (unchanged semantics)
# ──────────────────────────────────────────────────────────────────────────────


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
    """A total_simulation_time below the minimum constant raises."""
    too_small = TimeDefaults.MIN_SIMULATION_TIME - 1
    with pytest.raises(ValidationError):
        SimulationSettings(total_simulation_time=too_small)
