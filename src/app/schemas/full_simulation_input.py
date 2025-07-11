"""Definition of the full input for the simulation"""

from pydantic import BaseModel

from app.schemas.requests_generator_input import RqsGeneratorInput
from app.schemas.requests_handler_input import Endpoint


class SimulationPayload(BaseModel):
    """Full input structure to perform a simulation"""

    rqs_input: RqsGeneratorInput
    all_endpoints: list[Endpoint]
