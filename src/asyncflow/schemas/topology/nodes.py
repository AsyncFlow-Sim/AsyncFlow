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

from asyncflow.config.constants import (
    LbAlgorithmsName,
    ServerResourcesDefaults,
    SystemNodes,
)
from asyncflow.schemas.topology.endpoint import Endpoint

#-------------------------------------------------------------
# Definition of the nodes structure for the graph representing
# the topoogy of the system defined for the simulation
#-------------------------------------------------------------

# -------------------------------------------------------------
# CLIENT
# -------------------------------------------------------------

class Client(BaseModel):
    """Definition of the client class"""

    id: str
    type: SystemNodes = SystemNodes.CLIENT

    @field_validator("type", mode="after")
    def ensure_type_is_standard(cls, v: SystemNodes) -> SystemNodes: # noqa: N805
        """Ensure the type of the client is standard"""
        if v != SystemNodes.CLIENT:
            msg = f"The type should have a standard value: {SystemNodes.CLIENT}"
            raise ValueError(msg)
        return v

# -------------------------------------------------------------
# SERVER RESOURCES
# -------------------------------------------------------------

class ServerResources(BaseModel):
    """
    Defines the quantifiable resources available on a server node.
    Each attribute maps directly to a SimPy resource primitive.
    """

    cpu_cores: PositiveInt = Field(
        ServerResourcesDefaults.CPU_CORES,
        ge = ServerResourcesDefaults.MINIMUM_CPU_CORES,
        description="Number of CPU cores available for processing.",
    )
    db_connection_pool: PositiveInt | None = Field(
        ServerResourcesDefaults.DB_CONNECTION_POOL,
        description="Size of the database connection pool, if applicable.",
    )

    # Risorse modellate come simpy.Container (livello)
    ram_mb: PositiveInt = Field(
        ServerResourcesDefaults.RAM_MB,
        ge = ServerResourcesDefaults.MINIMUM_RAM_MB,
        description="Total available RAM in Megabytes.")

    # for the future
    # disk_iops_limit: PositiveInt | None = None
    # network_throughput_mbps: PositiveInt | None = None

# -------------------------------------------------------------
# SERVER
# -------------------------------------------------------------

class Server(BaseModel):
    """
    definition of the server class:
    - id: is the server identifier
    - type: is the type of node in the structure
    - server resources: is a dictionary to define the resources
      of the machine where the server is living
    - endpoints: is the list of all endpoints in a server
    """

    id: str
    type: SystemNodes = SystemNodes.SERVER
    #Later define a valide structure for the keys of server resources
    server_resources : ServerResources
    endpoints : list[Endpoint]

    @field_validator("type", mode="after")
    def ensure_type_is_standard(cls, v: SystemNodes) -> SystemNodes: # noqa: N805
        """Ensure the type of the server is standard"""
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



    @field_validator("type", mode="after")
    def ensure_type_is_standard(cls, v: SystemNodes) -> SystemNodes: # noqa: N805
        """Ensure the type of the server is standard"""
        if v != SystemNodes.LOAD_BALANCER:
            msg = f"The type should have a standard value: {SystemNodes.LOAD_BALANCER}"
            raise ValueError(msg)
        return v


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
    load_balancer: LoadBalancer | None = None

    @model_validator(mode="after") # type: ignore[arg-type]
    def unique_ids(
        cls, # noqa: N805
        model: "TopologyNodes",
        ) -> "TopologyNodes":
        """Check that all id are unique"""
        ids = [server.id for server in model.servers] + [model.client.id]

        if model.load_balancer is not None:
            ids.append(model.load_balancer.id)

        counter = Counter(ids)
        duplicate = [node_id for node_id, value in counter.items() if value > 1]
        if duplicate:
            msg = f"The following node ids are duplicate {duplicate}"
            raise ValueError(msg)
        return model

    model_config = ConfigDict(extra="forbid")
