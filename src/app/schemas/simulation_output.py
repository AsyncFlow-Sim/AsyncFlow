"""Define the output of the simulation"""

from pydantic import BaseModel


class SimulationOutput(BaseModel):
    """Define the output of the simulation"""

    total_requests: dict[str, int | float]
    # TO DEFINE
    metric_2: str
    #......
    metric_n: str
