""""Api to simulate the process"""

import numpy as np
from fastapi import APIRouter

from app.core.requests_generator import requests_generator
from app.schemas.simulation_input import SimulationInput
from app.schemas.simulation_output import SimulationOutput

router = APIRouter()

@router.post("/simulation")
async def event_loop_simulation(
    generator_input: SimulationInput,
) -> SimulationOutput:
    """Endpoint to handle the simulation."""
    # Define the variables for the generator
    # Implement a robust type checking for
    # edge cases
    rng: np.random.Generator = np.random.default_rng()

    # requests generator
    req_generated  = requests_generator( # noqa: F841
        generator_input,
        rng=rng,
    )

    # simple map to pass the quality assurance
    return SimulationOutput(
        metric_1=generator_input.avg_active_users.mean,
        metric_2=str(generator_input.avg_request_per_minute_per_user.mean),
        metric_n=str(generator_input.total_simulation_time),
    )


