"""Define the schemas for the simulator"""

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

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
    total_simulation_time: int | None = None

    @field_validator("total_simulation_time", mode="before")
    def check_simulation_time(cls, v: object) -> int: # noqa: N805
        """
        Assign constant value to total sim time if is None
        check if it is of the right type
        impose a lower boundary for the simulation
        """
        if v is None:
            v = TimeDefaults.SIMULATION_HORIZON.value
        if not isinstance(v, int):
            err_msg_type = "the simulation time must be an integer"
            raise ValueError(err_msg_type) # noqa: TRY004
        if v <= 60:
            err_msg_val = "the simulation must be at least 60 seconds"
            raise ValueError(err_msg_val)
        return v

