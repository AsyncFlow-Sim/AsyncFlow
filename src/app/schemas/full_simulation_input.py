"""Definition of the full input for the simulation"""

from pydantic import BaseModel

from app.schemas.rqs_generator_input import RqsGeneratorInput
from app.schemas.simulation_settings_input import SimulationSettings
from app.schemas.system_topology.full_system_topology import TopologyGraph


class SimulationPayload(BaseModel):
    """Full input structure to perform a simulation"""

    rqs_input: RqsGeneratorInput
    topology_graph: TopologyGraph
    sim_settings: SimulationSettings
