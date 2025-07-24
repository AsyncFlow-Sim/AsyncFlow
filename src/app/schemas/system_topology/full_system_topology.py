"""
Define the topology of the system as a directed graph
where nodes represents macro structure (server, client ecc ecc)
and edges how these strcutures are connected and the network
latency necessary for the requests generated to move from
one structure to another
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

from app.config.constants import (
    NetworkParameters,
    ServerResourcesDefaults,
    SystemEdges,
    SystemNodes,
)
from app.schemas.random_variables_config import RVConfig
from app.schemas.system_topology.endpoint import Endpoint

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
# SERVER RESOURCES EXAMPLE
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

    @model_validator(mode="after") # type: ignore[arg-type]
    def unique_ids(
        cls, # noqa: N805
        model: "TopologyNodes",
        ) -> "TopologyNodes":
        """Check that all id are unique"""
        ids = [server.id for server in model.servers] + [model.client.id]
        counter = Counter(ids)
        duplicate = [node_id for node_id, value in counter.items() if value > 1]
        if duplicate:
            msg = f"The following node ids are duplicate {duplicate}"
            raise ValueError(msg)
        return model

    model_config = ConfigDict(extra="forbid")

#-------------------------------------------------------------
# Definition of the edges structure for the graph representing
# the topoogy of the system defined for the simulation
#-------------------------------------------------------------

class Edge(BaseModel):
    """
    A directed connection in the topology graph.

    Attributes
    ----------
    source : str
        Identifier of the source node (where the request comes from).
    target : str
        Identifier of the destination node (where the request goes to).
    latency : RVConfig
        Random-variable configuration for network latency on this link.
    probability : float
        Probability of taking this edge when there are multiple outgoing links.
        Must be in [0.0, 1.0]. Defaults to 1.0 (always taken).
    edge_type : SystemEdges
        Category of the link (e.g. network, queue, stream).

    """

    id: str
    source: str
    target: str
    latency: RVConfig
    probability: float = Field(1.0, ge=0.0, le=1.0)
    edge_type: SystemEdges = SystemEdges.NETWORK_CONNECTION
    dropout_rate: float = Field(
        NetworkParameters.DROPOUT_RATE,
        ge = NetworkParameters.MIN_DROPOUT_RATE,
        le = NetworkParameters.MAX_DROPOUT_RATE,
        description=(
            "for each nodes representing a network we define"
            "a probability to drop the request"
        ),
    )

    @model_validator(mode="after") # type: ignore[arg-type]
    def check_src_trgt_different(cls, model: "Edge") -> "Edge": # noqa: N805
        """Ensure source is different from target"""
        if model.source == model.target:
            msg = "source and target must be different nodes"
            raise ValueError(msg)
        return model


#-------------------------------------------------------------
# Definition of the Graph structure representing
# the topogy of the system defined for the simulation
#-------------------------------------------------------------

class TopologyGraph(BaseModel):
    """
    data collection for the whole graph representing
    the full system
    """

    nodes: TopologyNodes
    edges: list[Edge]

    @model_validator(mode="after") # type: ignore[arg-type]
    def unique_ids(
        cls, # noqa: N805
        model: "TopologyGraph",
        ) -> "TopologyGraph":
        """Check that all id are unique"""
        counter = Counter(edge.id for edge in model.edges)
        duplicate = [edge_id for edge_id, value in counter.items() if value > 1]
        if duplicate:
            msg = f"There are multiple edges with the following ids {duplicate}"
            raise ValueError(msg)
        return model


    @model_validator(mode="after") # type: ignore[arg-type]
    def edge_refs_valid(cls, model: "TopologyGraph") -> "TopologyGraph": # noqa: N805
        """
        Ensure that **every** edge points to valid nodes.

        The validator is executed *after* the entire ``TopologyGraph`` model has
        been built, so all servers and the client already exist in ``m.nodes``.

        Steps
        -----
        1. Build the set ``valid_ids`` containing:
        * all ``Server.id`` values, **plus**
        * the single ``Client.id``.
        2. Iterate through each ``Edge`` in ``m.edges`` and raise
        :class:`ValueError` if either ``edge.source`` or ``edge.target`` is
        **not** present in ``valid_ids``.

        Returning the (unchanged) model signals that the integrity check passed.
        """
        valid_ids = {s.id for s in model.nodes.servers} | {model.nodes.client.id}
        for e in model.edges:
            if e.source not in valid_ids or e.target not in valid_ids:
                msg = f"Edge {e.source}->{e.target} references unknown node"
                raise ValueError(msg)
        return model


