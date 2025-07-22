"""
Definition of support structures for the simulation runtime.

After Pydantic validation, this module provides TypedDicts and helpers
to build SimPy Containers for each server in the topology, improving
readability and ensuring a single point of truth for resource setup.
"""

from enum import StrEnum
from typing import TypedDict

import simpy

from app.schemas.system_topology_schema.full_system_topology_schema import (
        ServerResources,
    )

# ==============================================================
# DICT FOR THE REGISTRY TO INITIALIZE RESOURCES FOR EACH SERVER
# ==============================================================

# enum in this case is to have the availabale key and improve
#code readability not for the validation

class ServerResourceName(StrEnum):
    """Keys for each server resource type, used when building the container map."""

    CPU = "CPU"
    RAM = "RAM"

class ServerContainers(TypedDict):
    """
    Mapping of resource names to their SimPy Container instances for a server.

    - CPU: simpy.Container for CPU cores.
    - RAM: simpy.Container for RAM in megabytes.
    """

    CPU: simpy.Container
    RAM: simpy.Container

# Central funcrion to initialize  the dictionary with ram and cpu container
def build_containers(
    env: simpy.Environment,
    spec: ServerResources,
    ) -> ServerContainers:
    """
    Construct and return a mapping of SimPy Containers for a server's CPU and RAM.

    Given a SimPy environment and a validated ServerResources spec, this function
    initializes one simpy.Container for CPU (with capacity equal to cpu_cores)
    and one for RAM (with capacity equal to ram_mb), then returns them in a
    ServerContainers TypedDict keyed by "CPU" and "RAM".

    Parameters
    ----------
    env : simpy.Environment
        The simulation environment in which the Containers will be created.
    spec : ServerResources
        A Pydantic model instance defining the server's cpu_cores and ram_mb.

    Returns
    -------
    ServerContainers
        A TypedDict with exactly two entries:
        - "CPU":   simpy.Container initialized with spec.cpu_cores
        - "RAM":   simpy.Container initialized with spec.ram_mb

    """
    return {
        ServerResourceName.CPU.value: simpy.Container(env, capacity=spec.cpu_cores),
        ServerResourceName.RAM.value: simpy.Container(env, capacity=spec.ram_mb),
    }





