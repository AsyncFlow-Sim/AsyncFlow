"""
Define the property of the edges of the system representing
links between different nodes
"""

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core.core_schema import ValidationInfo

from asyncflow.config.constants import (
    NetworkParameters,
    SystemEdges,
)
from asyncflow.schemas.common.random_variables import RVConfig

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
                "must be non negative"
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


