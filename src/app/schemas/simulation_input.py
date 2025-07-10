"""Define the schemas for the simulator"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config.constants import TimeDefaults


class RVConfig(BaseModel):
    """class to configure random variables"""

    mean: float
    distribution: Literal["poisson", "normal", "gaussian"] = "poisson"
    variance: float | None = None

    @field_validator("mean", mode="before")
    def check_mean_is_number(
        cls, # noqa: N805
        v: object,
        ) -> float:
        """Ensure `mean` is numeric, then coerce to float."""
        err_msg = "mean must be a number (int or float)"
        if not isinstance(v, (float, int)):
            raise ValueError(err_msg)  # noqa: TRY004
        return float(v)

    @model_validator(mode="after")  # type: ignore[arg-type]
    def default_variance(cls, model: "RVConfig") -> "RVConfig":  # noqa: N805
        """Set variance = mean when distribution == 'normal' and variance is missing."""
        if model.variance is None and model.distribution in {"normal", "gaussian"}:
            model.variance = model.mean
        return model

class SimulationInput(BaseModel):
    """Define the expected variables for the simulation"""

    avg_active_users: RVConfig
    avg_request_per_minute_per_user: RVConfig
    total_simulation_time: int = Field(
        default=TimeDefaults.SIMULATION_TIME.value,
        ge=TimeDefaults.MIN_SIMULATION_TIME.value, # minimum simulation time in seconds
        description=(
            f"Simulation time in seconds (>= {TimeDefaults.MIN_SIMULATION_TIME.value})."
        ),
    )

    user_sampling_window: int = Field(
        default=TimeDefaults.USER_SAMPLING_WINDOW.value,
        ge=TimeDefaults.MIN_USER_SAMPLING_WINDOW.value,
        le=TimeDefaults.MAX_USER_SAMPLING_WINDOW.value,
        description=(
            "Sampling window in seconds "
            f"({TimeDefaults.MIN_USER_SAMPLING_WINDOW.value}-"
            f"{TimeDefaults.MAX_USER_SAMPLING_WINDOW.value})."
        ),
    )


