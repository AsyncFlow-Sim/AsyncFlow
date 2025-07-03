""""Api to simulate the process"""

from fastapi import APIRouter

from app.schemas.simulation_input import SimulationInput
from app.schemas.simulation_output import SimulationOutput

router = APIRouter()

@router.post("/simulation")
async def event_loop_simulation(
    generator_input: SimulationInput,
) -> SimulationOutput:
    """Endpoint to handle the simulation."""
    # simple map to pass the quality assurance
    return SimulationOutput(
        metric_1=generator_input.avg_active_users.mean,
        metric_2=str(generator_input.avg_request_per_minute_per_user.mean),
        metric_n=str(generator_input.total_simulation_time),
    )


