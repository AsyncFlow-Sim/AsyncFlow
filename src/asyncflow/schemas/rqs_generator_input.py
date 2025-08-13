"""Define the schemas for the simulator"""


from pydantic import BaseModel, Field, field_validator

from asyncflow.config.constants import Distribution, SystemNodes, TimeDefaults
from asyncflow.schemas.random_variables_config import RVConfig


class RqsGeneratorInput(BaseModel):
    """Define the expected variables for the simulation"""

    id: str
    type: SystemNodes = SystemNodes.GENERATOR
    avg_active_users: RVConfig
    avg_request_per_minute_per_user: RVConfig

    user_sampling_window: int = Field(
        default=TimeDefaults.USER_SAMPLING_WINDOW,
        ge=TimeDefaults.MIN_USER_SAMPLING_WINDOW,
        le=TimeDefaults.MAX_USER_SAMPLING_WINDOW,
        description=(
            "Sampling window in seconds "
            f"({TimeDefaults.MIN_USER_SAMPLING_WINDOW}-"
            f"{TimeDefaults.MAX_USER_SAMPLING_WINDOW})."
        ),
    )

    @field_validator("avg_request_per_minute_per_user", mode="after")
    def ensure_avg_request_is_poisson(
        cls, # noqa: N805
        v: RVConfig,
        ) -> RVConfig:
        """
        Force the distribution for the rqs generator to be poisson
        at the moment we have a joint sampler just for the poisson-poisson
        and gaussian-poisson case
        """
        if v.distribution != Distribution.POISSON:
            msg = "At the moment the variable avg request must be Poisson"
            raise ValueError(msg)
        return v

    @field_validator("avg_active_users", mode="after")
    def ensure_avg_user_is_poisson_or_gaussian(
        cls, # noqa: N805
        v: RVConfig,
        ) -> RVConfig:
        """
        Force the distribution for the rqs generator to be poisson
        at the moment we have a joint sampler just for the poisson-poisson
        and gaussian-poisson case
        """
        if v.distribution not in {Distribution.POISSON, Distribution.NORMAL}:
            msg = "At the moment the variable active user must be Poisson or Gaussian"
            raise ValueError(msg)
        return v


