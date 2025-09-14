"""
Define the pydantic schemas of the nodes you are allowed
to define in the topology of the system you would like to
simulate
"""

from collections import Counter

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from asyncflow.config.constants import NodesResourcesDefaults
from asyncflow.config.enums import (
    LbAlgorithmsName,
    SystemNodes,
)
from asyncflow.schemas.topology.endpoint import Endpoint

#-------------------------------------------------------------
# Definition of the nodes structure for the graph representing
# the topology of the system defined for the simulation
#-------------------------------------------------------------

# -------------------------------------------------------------
# Resources you may assign to a node
# -------------------------------------------------------------

class NodesResources(BaseModel):
    """
    Quantifiable resources available on a node (server/LB/client).
    Each attribute maps to a SimPy resource primitive or container.
    """

    cpu_cores: PositiveInt = Field(
        NodesResourcesDefaults.CPU_CORES,
        ge = NodesResourcesDefaults.MINIMUM_CPU_CORES,
        description="Number of CPU cores available for processing.",
    )

    db_connection_pool: PositiveInt | None = Field(
        NodesResourcesDefaults.DB_CONNECTION_POOL,
        description="Size of the database connection pool, if applicable.",
    )

    ram_mb: PositiveInt = Field(
        NodesResourcesDefaults.RAM_MB,
        ge = NodesResourcesDefaults.MINIMUM_RAM_MB,
        description="Total available RAM in megabytes.")

# -------------------------------------------------------------
# CLIENT
# -------------------------------------------------------------

class Client(BaseModel):
    """Definition of the client class"""

    id: str
    type: SystemNodes = SystemNodes.CLIENT

    # A client may be hosted on a virtual machine
    # and technically has resources.
    # At this stage, client-side bottlenecks
    # are not modeled, so resources are optional.

    client_resources: NodesResources | None = None
    ram_per_process: PositiveInt | None = None

    @field_validator("type", mode="after")
    def ensure_type_is_standard(cls, v: SystemNodes) -> SystemNodes: # noqa: N805
        """Ensure the node type is CLIENT."""
        if v != SystemNodes.CLIENT:
            msg = f"The type should have a standard value: {SystemNodes.CLIENT}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after") # type: ignore[arg-type]
    def ram_and_ram_per_process_are_coherent(
        cls, # noqa: N805
        model: "Client",
        ) -> "Client":
        """Check that if ram per process exist, ram is assigned to the client"""
        if model.ram_per_process and not model.client_resources:
            msg = ("To reserve per-process RAM for the client "
                   f"'{model.id}', define resources in 'client_resources'.")
            raise ValueError(msg)

        return model



# -------------------------------------------------------------
# SERVER
# -------------------------------------------------------------

class Server(BaseModel):
    """
    definition of the server class:
    - id: is the server identifier
    - type: is the type of node in the structure
    - nodes resources: is a dictionary to define the resources
      of the machine where the server is living
    - endpoints: is the list of all endpoints in a server
    """

    id: str
    type: SystemNodes = SystemNodes.SERVER
    server_resources: NodesResources
    endpoints: list[Endpoint] = Field(min_length=1)
    ram_per_process: PositiveInt | None = None

    @field_validator("type", mode="after")
    def ensure_type_is_standard(cls, v: SystemNodes) -> SystemNodes: # noqa: N805
        """Ensure the node type is SERVER."""
        if v != SystemNodes.SERVER:
            msg = f"The type should have a standard value: {SystemNodes.SERVER}"
            raise ValueError(msg)
        return v

class LoadBalancer(BaseModel):
    """
    basemodel for the load balancer
    - id: unique name associated to the lb
    - type: type of the node in the structure
    - server_covered: list of server id connected to the lb
    """

    id: str
    type: SystemNodes = SystemNodes.LOAD_BALANCER
    algorithms: LbAlgorithmsName = LbAlgorithmsName.ROUND_ROBIN
    server_covered: set[str] = Field(default_factory=set)

    # In the next release, once the new network model is introduced,
    # we will monitor resource-related bottlenecks that can occur at the LB,
    # especially RAM pressure. Until then, we keep this optional to maintain
    # compatibility with the current public API.
    lb_resources: NodesResources | None = None
    ram_per_process: PositiveInt | None = None


    @field_validator("type", mode="after")
    def ensure_type_is_standard(cls, v: SystemNodes) -> SystemNodes: # noqa: N805
        """Ensure the node type is LOAD_BALANCER."""
        if v != SystemNodes.LOAD_BALANCER:
            msg = f"The type should have a standard value: {SystemNodes.LOAD_BALANCER}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after") # type: ignore[arg-type]
    def ram_and_ram_per_process_are_coherent(
        cls, # noqa: N805
        model: "LoadBalancer",
        ) -> "LoadBalancer":
        """Check that if ram per process exist, ram is assigned to LB"""
        if model.ram_per_process and not model.lb_resources:
            msg = ("To reserve per-process RAM for the load balancer "
                   f"'{model.id}', define resources in 'lb_resources'.")
            raise ValueError(msg)

        return model


# -------------------------------------------------------------
# NODES CLASS WITH ALL POSSIBLE OBJECTS REPRESENTED BY A NODE
# -------------------------------------------------------------

class TopologyNodes(BaseModel):
    """
    Definition of the nodes class:
    - server: represent all servers implemented in the system
    - client: is a simple object with just a name representing
      the origin of the graph
    """

    servers: list[Server]
    client: Client

    # For now we accept a single LB; this may change in the future.
    load_balancer: LoadBalancer | None = None

    @model_validator(mode="after") # type: ignore[arg-type]
    def unique_ids(
        cls, # noqa: N805
        model: "TopologyNodes",
        ) -> "TopologyNodes":
        """Ensure that all node IDs are unique."""
        ids = [server.id for server in model.servers] + [model.client.id]

        if model.load_balancer is not None:
            ids.append(model.load_balancer.id)

        counter = Counter(ids)
        duplicate = [node_id for node_id, value in counter.items() if value > 1]
        if duplicate:
            msg = f"Duplicate node IDs detected: {duplicate}"
            raise ValueError(msg)
        return model

    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_servers_covered_by_lb_exist(
        cls, # noqa: N805
        model: "TopologyNodes",
        ) -> "TopologyNodes":
        """Ensure that all servers covered by the LB exist."""
        if not model.load_balancer:
            return model

        server_ids = {server.id for server in model.servers}

        for server_id in model.load_balancer.server_covered:
            if server_id not in server_ids:
                msg = (
                       f"Load balancer '{model.load_balancer.id}' "
                       f"references unknown server '{server_id}'. "
                       "Define it under 'servers' or remove it from 'server_covered'."
                       )
                raise ValueError(msg)

        return model

    @model_validator(mode="after") # type: ignore[arg-type]
    def ensure_ram_and_ram_per_process_is_valid(
        cls, # noqa: N805
        model: "TopologyNodes",
        ) -> "TopologyNodes":
        """Ensure the total ram for processes is not higher than the ram available"""
        for server in model.servers:
            if server.ram_per_process:
               total_ram_for_processes = (
                   server.server_resources.cpu_cores *
                   server.ram_per_process
               )
               if total_ram_for_processes >= server.server_resources.ram_mb:
                   msg = (f"Server '{server.id}': "
                          f"per-process RAM total ({total_ram_for_processes} MB) "
                          f"exceeds or is equal to total RAM "
                          f"({server.server_resources.ram_mb} MB)."
                   )
                   raise ValueError(msg)

        return model


    # Reject unknown fields to keep schemas strict and predictable.
    model_config = ConfigDict(extra="forbid")
