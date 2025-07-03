import pytest
from pydantic import ValidationError

from app.schemas.simulation_input import RVConfig

# --------------------------------------------------------------------------- #
# Positive cases                                                              #
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Validation errors                                                           #
# --------------------------------------------------------------------------- #

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
