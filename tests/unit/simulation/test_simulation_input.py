import pytest
from pydantic import ValidationError

from app.schemas.simulation_input import RVConfig, SimulationInput


def test_normal_sets_variance_to_mean() -> None:
    """When distribution='normal' and variance is omitted, variance == mean."""
    cfg = RVConfig(mean=10, distribution="normal")
    assert cfg.variance == 10.0


def test_poisson_keeps_variance_none() -> None:
    """When distribution='poisson' and variance is omitted, variance stays None."""
    cfg = RVConfig(mean=5, distribution="poisson")
    assert cfg.variance is None


def test_explicit_variance_is_preserved() -> None:
    """If the user supplies variance explicitly, it is preserved unchanged."""
    cfg = RVConfig(mean=8, distribution="normal", variance=4)
    assert cfg.variance == 4.0


def test_mean_must_be_numeric() -> None:
    """A non-numeric mean raises a ValidationError with our custom message."""
    with pytest.raises(ValidationError) as excinfo:
        RVConfig(mean="not a number", distribution="poisson")

    # Check that at least one error refers to the 'mean' field
    assert any(err["loc"] == ("mean",) for err in excinfo.value.errors())
    assert "mean must be a number" in excinfo.value.errors()[0]["msg"]


def test_missing_mean_field() -> None:
    """Omitting the mean field raises a 'field required' ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        # Using model_validate avoids the constructor signature check
        RVConfig.model_validate({"distribution": "normal"})

    assert any(
        err["loc"] == ("mean",) and err["type"] == "missing"
        for err in excinfo.value.errors()
    )

def test_gaussian_sets_variance_to_mean() -> None:
    """When distribution='gaussian' and variance is omitted, variance == mean."""
    cfg = RVConfig(mean=12.5, distribution="gaussian")
    assert cfg.variance == pytest.approx(12.5)


def test_default_distribution_is_poisson() -> None:
    """
    When distribution is omitted, it defaults to 'poisson' and
    variance stays None.
    """
    cfg = RVConfig(mean=3.3)
    assert cfg.distribution == "poisson"
    assert cfg.variance is None


def test_explicit_variance_kept_for_poisson() -> None:
    """If the user supplies variance even for poisson, it is preserved."""
    cfg = RVConfig(mean=4.0, distribution="poisson", variance=2.2)
    assert cfg.variance == pytest.approx(2.2)


def test_invalid_distribution_raises() -> None:
    """Supplying a non-supported distribution literal raises ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        RVConfig(mean=5.0, distribution="not_a_dist")

    errors = excinfo.value.errors()
    # Only assert there is at least one error for the 'distribution' field:
    assert any(e["loc"] == ("distribution",) for e in errors)


def test_simulation_time_below_minimum_raises() -> None:
    """
    Passing total_simulation_time <= 60 must raise a ValidationError,
    because the minimum allowed simulation time is 61 seconds.
    """
    with pytest.raises(ValidationError) as excinfo:
        SimulationInput(
            avg_active_users={"mean": 1.0},
            avg_request_per_minute_per_user={"mean": 1.0},
            total_simulation_time=60,  # exactly at the boundary
        )
    errors = excinfo.value.errors()
    assert any(
        err["loc"] == ("total_simulation_time",) and "at least 60seconds" in err["msg"]
        for err in errors
    )
