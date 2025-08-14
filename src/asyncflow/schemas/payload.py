"""Definition of the full input for the simulation"""

from pydantic import BaseModel

from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.workload.rqs_generator import RqsGenerator


class SimulationPayload(BaseModel):
    """Full input structure to perform a simulation"""

    rqs_input: RqsGenerator
    topology_graph: TopologyGraph
    sim_settings: SimulationSettings
