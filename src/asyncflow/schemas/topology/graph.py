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
    model_validator,
)

from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.nodes import TopologyNodes

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
        Check the validity of the load balancer: first we check
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
                  f"references unknown servers: {sorted(missing)}")
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


    @model_validator(mode="after")  # type: ignore[arg-type]
    def no_fanout_except_lb(cls, model: "TopologyGraph") -> "TopologyGraph":  # noqa: N805
        """Ensure only the LB (declared node) can have multiple outgoing edges."""
        lb_id = model.nodes.load_balancer.id if model.nodes.load_balancer else None

        # let us consider only nodes declared in the topology
        node_ids: set[str] = {server.id for server in model.nodes.servers}
        node_ids.add(model.nodes.client.id)
        if lb_id:
            node_ids.add(lb_id)

        counts: dict[str, int] = {}
        for edge in model.edges:
            if edge.source not in node_ids:
                continue
            counts[edge.source] = counts.get(edge.source, 0) + 1

        offenders = [src for src, c in counts.items() if c > 1 and src != lb_id]
        if offenders:
            msg = (
                "Only the load balancer can have multiple outgoing edges. "
                f"Offending sources: {offenders}"
            )
            raise ValueError(msg)

        return model
