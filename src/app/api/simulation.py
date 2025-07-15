""""Api to simulate the process"""

import numpy as np
from fastapi import APIRouter

from app.core.simulation.simulation_run import run_simulation
from app.schemas.full_simulation_input import SimulationPayload
from app.schemas.simulation_output import SimulationOutput

router = APIRouter()

@router.post("/simulation")
async def event_loop_simulation(input_data: SimulationPayload) -> SimulationOutput:
    """Run the simulation and return aggregate KPIs."""
    rng = np.random.default_rng()
    return run_simulation(input_data, rng=rng)


