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
from pydantic_core.core_schema import ValidationInfo

from app.config.constants import (
    LbAlgorithmsName,
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

    # The idea to put here the control about variance and mean about the edges
    # latencies and not in RVConfig is to provide a better error handling
    # providing a direct indication of the edge with the error
    # The idea to put here the control about variance and mean about the edges
    # latencies and not in RVConfig is to provide a better error handling
    # providing a direct indication of the edge with the error
    @field_validator("latency", mode="after")
    def ensure_latency_is_non_negative(
        cls, # noqa: N805
        v: RVConfig,
        info: ValidationInfo,
        ) -> RVConfig:
        """Ensures that the latency's mean and variance are positive."""
        mean = v.mean
        variance = v.variance

        # We can get the edge ID from the validation context for a better error message
        edge_id = info.data.get("id", "unknown")

        if mean <= 0:
            msg = f"The mean latency of the edge '{edge_id}' must be positive"
            raise ValueError(msg)
        if variance is not None and variance < 0: # Variance can be zero
            msg = (
                f"The variance of the latency of the edge {edge_id}"
                "must be positive"
            )
            raise ValueError(msg)
        return v


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


    @model_validator(mode="after")  # type: ignore[arg-type]
    def edge_refs_valid(
        cls,                         # noqa: N805
        model: "TopologyGraph",
    ) -> "TopologyGraph":
        """
        Validate that the graph is self-consistent.

        * All targets must be nodes declared in ``m.nodes``.
        * External IDs are allowed as sources (entry points, generator) but
          they must never appear as a target anywhere else.
        """
        # ------------------------------------------------------------------
        # 1. Collect declared node IDs (servers, client, optional LB)
        # ------------------------------------------------------------------
        node_ids: set[str] = {srv.id for srv in model.nodes.servers}
        node_ids.add(model.nodes.client.id)
        if model.nodes.load_balancer is not None:
            node_ids.add(model.nodes.load_balancer.id)

        # ------------------------------------------------------------------
        # 2. Scan every edge once
        # ------------------------------------------------------------------
        external_sources: set[str] = set()

        for edge in model.edges:
            # ── Rule 1: target must be a declared node
            if edge.target not in node_ids:
                msg = (
                    f"Edge {edge.source}->{edge.target} references "
                    f"unknown target node '{edge.target}'."
                )
                raise ValueError(msg)

            # Collect any source that is not a declared node
            if edge.source not in node_ids:
                external_sources.add(edge.source)

        # ------------------------------------------------------------------
        # 3. Ensure external sources never appear as targets elsewhere
        # ------------------------------------------------------------------
        forbidden_targets = external_sources & {e.target for e in model.edges}
        if forbidden_targets:
            msg = (
                "External IDs cannot be used as targets as well:"
                f"{sorted(forbidden_targets)}"
                )
            raise ValueError(msg)

        return model

    @model_validator(mode="after") # type: ignore[arg-type]
    def valid_load_balancer(cls, model: "TopologyGraph") -> "TopologyGraph": # noqa: N805
        """
        Check de validity of the load balancer: first we check
        if is present in the simulation, second we check if the LB list
        is a proper subset of the server sets of ids, then we check if
        edge from LB to the servers are well defined
        """
        lb = model.nodes.load_balancer
        if lb is None:
            return model

        server_ids = {s.id for s in model.nodes.servers}

        # 1) LB list ⊆ server_ids
        missing = lb.server_covered - server_ids
        if missing:

            msg = (f"Load balancer '{lb.id}'"
                  "references unknown servers: {sorted(missing)}")
            raise ValueError(msg)

        # edge are well defined
        targets_from_lb = {e.target for e in model.edges if e.source == lb.id}
        not_linked = lb.server_covered - targets_from_lb
        if not_linked:
            msg = (
                    f"Servers {sorted(not_linked)} are covered by LB '{lb.id}' "
                    "but have no outgoing edge from it."
                )

            raise ValueError(msg)

        return model


