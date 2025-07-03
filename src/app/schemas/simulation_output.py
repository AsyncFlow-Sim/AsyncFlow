"""Define the output of the simulation"""

from pydantic import BaseModel


class SimulationOutput(BaseModel):
    """Define the output of the simulation"""

    metric_1: str | int
    metric_2: str
    #......
    metric_n: str
