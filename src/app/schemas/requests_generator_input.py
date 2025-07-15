"""Define the schemas for the simulator"""


from pydantic import BaseModel, Field

from app.config.constants import TimeDefaults
from app.schemas.random_variables_config import RVConfig


class RqsGeneratorInput(BaseModel):
    """Define the expected variables for the simulation"""

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


