""""Api to simulate the process"""

import numpy as np
from fastapi import APIRouter

from app.core.simulation.simulation_run import run_simulation
from app.schemas.requests_generator_input import RqsGeneratorInput
from app.schemas.simulation_output import SimulationOutput

router = APIRouter()

@router.post("/simulation")
async def event_loop_simulation(input_data: RqsGeneratorInput) -> SimulationOutput:
    """Run the simulation and return aggregate KPIs."""
    rng = np.random.default_rng()
    return run_simulation(input_data, rng=rng)


