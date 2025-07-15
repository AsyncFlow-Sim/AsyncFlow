"""define a class with the global settings for the simulation"""

from pydantic import BaseModel, Field

from app.config.constants import TimeDefaults


class SimulationSettings(BaseModel):
    """Global parameters that apply to the whole run."""

    total_simulation_time: int = Field(
        default=TimeDefaults.SIMULATION_TIME,
        ge=TimeDefaults.MIN_SIMULATION_TIME,
        description="Simulation horizon in seconds.",
    )
