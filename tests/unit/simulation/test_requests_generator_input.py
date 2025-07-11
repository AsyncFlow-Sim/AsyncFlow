import pytest
from pydantic import ValidationError

from app.config.constants import Distribution, TimeDefaults
from app.schemas.requests_generator_input import RqsGeneratorInput, RVConfig

# --------------------------------------------------------------------------
# TEST RANDOM VARIABLE CONFIGURATION
# --------------------------------------------------------------------------

def test_normal_sets_variance_to_mean() -> None:
    """When distribution='normal' and variance is omitted, variance == mean."""
    cfg = RVConfig(mean=10, distribution=Distribution.NORMAL)
    assert cfg.variance == 10.0


def test_poisson_keeps_variance_none() -> None:
    """When distribution='poisson' and variance is omitted, variance stays None."""
    cfg = RVConfig(mean=5, distribution=Distribution.POISSON)
    assert cfg.variance is None


def test_explicit_variance_is_preserved() -> None:
    """If the user supplies variance explicitly, it is preserved unchanged."""
    cfg = RVConfig(mean=8, distribution=Distribution.NORMAL, variance=4)
    assert cfg.variance == 4.0


def test_mean_must_be_numeric() -> None:
    """A non-numeric mean raises a ValidationError with our custom message."""
    with pytest.raises(ValidationError) as excinfo:
        RVConfig(mean="not a number", distribution=Distribution.POISSON)

    # Check that at least one error refers to the 'mean' field
    assert any(err["loc"] == ("mean",) for err in excinfo.value.errors())
    assert "mean must be a number" in excinfo.value.errors()[0]["msg"]


def test_missing_mean_field() -> None:
    """Omitting the mean field raises a 'field required' ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        # Using model_validate avoids the constructor signature check
        RVConfig.model_validate({"distribution": Distribution.NORMAL})

    assert any(
        err["loc"] == ("mean",) and err["type"] == "missing"
        for err in excinfo.value.errors()
    )

def test_gaussian_sets_variance_to_mean() -> None:
    """When distribution='gaussian' and variance is omitted, variance == mean."""
    cfg = RVConfig(mean=12.5, distribution=Distribution.NORMAL)
    assert cfg.variance == pytest.approx(12.5)


def test_default_distribution_is_poisson() -> None:
    """
    When distribution is omitted, it defaults to 'poisson' and
    variance stays None.
    """
    cfg = RVConfig(mean=3.3)
    assert cfg.distribution == Distribution.POISSON
    assert cfg.variance is None


def test_explicit_variance_kept_for_poisson() -> None:
    """If the user supplies variance even for poisson, it is preserved."""
    cfg = RVConfig(mean=4.0, distribution=Distribution.POISSON, variance=2.2)
    assert cfg.variance == pytest.approx(2.2)


def test_invalid_distribution_raises() -> None:
    """Supplying a non-supported distribution literal raises ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        RVConfig(mean=5.0, distribution="not_a_dist")

    errors = excinfo.value.errors()
    # Only assert there is at least one error for the 'distribution' field:
    assert any(e["loc"] == ("distribution",) for e in errors)

# --------------------------------------------------------------------------
# TEST FIELD VALIDATOR USER SAMPLING WINDOW
# --------------------------------------------------------------------------

def test_default_user_sampling_window() -> None:
    """When user_sampling_window is omitted, it defaults to USER_SAMPLING_WINDOW."""
    inp = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
        avg_request_per_minute_per_user={
            "mean": 1.0,
            "distribution": Distribution.POISSON,
        },
    )
    assert inp.user_sampling_window == TimeDefaults.USER_SAMPLING_WINDOW


def test_explicit_user_sampling_window_kept() -> None:
    """An explicit user_sampling_window value is preserved unchanged."""
    custom_window = 30
    inp = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
        avg_request_per_minute_per_user={
            "mean": 1.0,
            "distribution": Distribution.POISSON,
        },
        user_sampling_window=custom_window,
    )
    assert inp.user_sampling_window == custom_window


def test_user_sampling_window_not_int_raises() -> None:
    """A non-integer user_sampling_window raises a ValidationError."""
    with pytest.raises(ValidationError) as excinfo:

        RqsGeneratorInput(
            avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
            avg_request_per_minute_per_user={
                "mean": 1.0,
                "distribution": Distribution.POISSON,
            },
            user_sampling_window="not-an-int",
        )

    errors = excinfo.value.errors()
    assert any(err["loc"] == ("user_sampling_window",) for err in errors)

    # Pydantic v2 wording
    assert any("valid integer" in err["msg"] for err in errors)



def test_user_sampling_window_above_max_raises() -> None:
    """
    Passing user_sampling_window > MAX_USER_SAMPLING_WINDOW
    must raise a ValidationError.
    """
    too_large = TimeDefaults.MAX_USER_SAMPLING_WINDOW + 1
    with pytest.raises(ValidationError) as excinfo:
        RqsGeneratorInput(
            avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
            avg_request_per_minute_per_user={
                "mean": 1.0,
                "distribution": Distribution.POISSON,
            },
            user_sampling_window=too_large,
        )

    errors = excinfo.value.errors()
    assert any(err["loc"] == ("user_sampling_window",) for err in errors)

    expected_snippet = (
        f"less than or equal to {TimeDefaults.MAX_USER_SAMPLING_WINDOW}"
    )
    assert any(expected_snippet in err["msg"] for err in errors)



# --------------------------------------------------------------------------
# TEST FIELD VALIDATOR TOTAL SIMULATION TIME
# --------------------------------------------------------------------------

def test_default_total_simulation_time() -> None:
    """When total_simulation_time is omitted, it defaults to SIMULATION_TIME."""
    inp = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
        avg_request_per_minute_per_user={
            "mean": 1.0,
            "distribution": Distribution.POISSON,
        },
    )
    assert inp.total_simulation_time == TimeDefaults.SIMULATION_TIME


def test_explicit_total_simulation_time_kept() -> None:
    """An explicit total_simulation_time value is preserved unchanged."""
    custom_time = 3_000
    inp = RqsGeneratorInput(
        avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
        avg_request_per_minute_per_user={
            "mean": 1.0,
            "distribution": Distribution.POISSON,
        },
        total_simulation_time=custom_time,
    )
    assert inp.total_simulation_time == custom_time


def test_total_simulation_time_not_int_raises() -> None:
    """A non-integer total_simulation_time raises a ValidationError."""
    with pytest.raises(ValidationError) as excinfo:

        RqsGeneratorInput(
            avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
            avg_request_per_minute_per_user={
                "mean": 1.0,
                "distribution": Distribution.POISSON,
            },
            total_simulation_time="three thousand",
        )

    errors = excinfo.value.errors()
    assert any(err["loc"] == ("total_simulation_time",) for err in errors)

    # Pydantic v2 wording: “Input should be a valid integer”
    assert any("valid integer" in err["msg"] for err in errors)



def test_total_simulation_time_below_minimum_raises() -> None:
    """
    Passing total_simulation_time < MIN_SIMULATION_TIME
    must raise a ValidationError.
    """
    too_small = TimeDefaults.MIN_SIMULATION_TIME - 1
    with pytest.raises(ValidationError) as excinfo:
        RqsGeneratorInput(
            avg_active_users={"mean": 1.0, "distribution": Distribution.POISSON},
            avg_request_per_minute_per_user={
                "mean": 1.0,
                "distribution": Distribution.POISSON,
            },
            total_simulation_time=too_small,
        )

    errors = excinfo.value.errors()
    # c'è almeno un errore sul campo giusto
    assert any(err["loc"] == ("total_simulation_time",) for err in errors)

    expected_snippet = (
        f"greater than or equal to {TimeDefaults.MIN_SIMULATION_TIME}"
    )
    assert any(expected_snippet in err["msg"] for err in errors)


