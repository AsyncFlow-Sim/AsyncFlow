"""Definition of the input of the simulation through python object"""

from __future__ import annotations

from typing import Self

from asyncflow.config.enums import EventDescription, SystemEdges
from asyncflow.schemas.arrivals.generator import ArrivalsGenerator
from asyncflow.schemas.events.injection import End, EventInjection, Start
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.edges import LinkEdge, NetworkEdge
from asyncflow.schemas.topology.graph import TopologyGraph
from asyncflow.schemas.topology.nodes import (
    Client,
    LoadBalancer,
    Server,
    TopologyNodes,
)


class AsyncFlow:
    """class with method to create the input for the simulation"""

    def __init__(self) -> None:
        """Instance attributes necessary to define the simulation payload"""
        self._arrivals: ArrivalsGenerator | None = None
        self._client: Client | None = None
        self._servers: list[Server] | None = None
        self._net_edges: list[NetworkEdge] | None = None
        self._link_edges: list[LinkEdge] | None = None
        self._sim_settings: SimulationSettings | None = None
        self._load_balancer: LoadBalancer | None = None
        self._events: list[EventInjection] = []
        self._edges_kind: SystemEdges | None = None

    def add_arrivals_generator(
        self,
        arrivals: ArrivalsGenerator,
        ) -> Self:
        """Method to instantiate the generator"""
        if not isinstance(arrivals, ArrivalsGenerator):
            msg = "You must add a ArrivalsGenerator instance"
            raise TypeError(msg)
        self._arrivals = arrivals
        return self

    def add_client(self, client: Client) -> Self:
        """Method to instantiate the client"""
        if not isinstance(client, Client):
            msg = "You must add a Client instance"
            raise TypeError(msg)

        self._client = client
        return self

    def add_servers(self, *servers: Server) -> Self:
        """Method to instantiate the server list"""
        if self._servers is None:
            self._servers = []

        for server in servers:
            if not isinstance(server, Server):
                msg = "All the instances must be of the type Server"
                raise TypeError(msg)
            self._servers.append(server)
        return self

    def add_edges(self, *edges: NetworkEdge | LinkEdge) -> Self:
        """Add edges; enforces homogeneous type (all NetworkEdge or all LinkEdge)."""
        if not edges:
            return self

        if self._edges_kind is None:
            first = edges[0]
            if isinstance(first, NetworkEdge):
                self._edges_kind = SystemEdges.NETWORK_CONNECTION
                self._net_edges = []
            elif isinstance(first, LinkEdge):
                self._edges_kind = SystemEdges.LINK_CONNECTION
                self._link_edges = []
            else:
                msg = "Edges must be NetworkEdge or LinkEdge."
                raise TypeError(msg)

        assert self._edges_kind is not None

        if self._edges_kind == SystemEdges.NETWORK_CONNECTION:
            assert self._net_edges is not None
            if any(not isinstance(e, NetworkEdge) for e in edges):
                msg = "Cannot mix LinkEdge with NetworkEdge."
                raise TypeError(msg)
            # ⬇️ Build a typed batch so mypy is happy
            net_batch: list[NetworkEdge] = [
                e for e in edges if isinstance(e, NetworkEdge)
            ]
            self._net_edges.extend(net_batch)
        else:
            assert self._link_edges is not None
            if any(not isinstance(e, LinkEdge) for e in edges):
                msg = "Cannot mix NetworkEdge with LinkEdge."
                raise TypeError(msg)
            # ⬇️ Typed batch for LinkEdge
            link_batch: list[LinkEdge] = [e for e in edges if isinstance(e, LinkEdge)]
            self._link_edges.extend(link_batch)

        return self



    def add_simulation_settings(self, sim_settings: SimulationSettings) -> Self:
        """Method to instantiate the settings for the simulation"""
        if not isinstance(sim_settings, SimulationSettings):
            msg = "The instance must be of the type SimulationSettings"
            raise TypeError(msg)

        self._sim_settings = sim_settings
        return self

    def add_load_balancer(self, load_balancer: LoadBalancer) -> Self:
        """Method to instantiate a load balancer"""
        if not isinstance(load_balancer, LoadBalancer):
            msg = "The instance must be of the type LoadBalancer"
            raise TypeError(msg)

        self._load_balancer = load_balancer
        return self

    # --------------------------------------------------------------------- #
    # Events                                                                #
    # --------------------------------------------------------------------- #

    def add_network_spike(
        self,
        *,
        event_id: str,
        edge_id: str,
        t_start: float,
        t_end: float,
        spike_s: float,
    ) -> Self:
        """Convenience: add a NETWORK_SPIKE on a given edge."""
        event = EventInjection(
            event_id=event_id,
            target_id=edge_id,
            start=Start(
                kind=EventDescription.NETWORK_SPIKE_START,
                t_start=t_start,
                spike_s=spike_s,
            ),
            end=End(
                kind=EventDescription.NETWORK_SPIKE_END,
                t_end=t_end,
            ),
        )

        self._events.append(event)
        return self

    def add_server_outage(
        self,
        *,
        event_id: str,
        server_id: str,
        t_start: float,
        t_end: float,
    ) -> Self:
        """Convenience: add a SERVER_DOWN → SERVER_UP window for a server."""
        event = EventInjection(
            event_id=event_id,
            target_id=server_id,
            start=Start(kind=EventDescription.SERVER_DOWN, t_start=t_start),
            end=End(kind=EventDescription.SERVER_UP, t_end=t_end),
        )
        self._events.append(event)
        return self

    def build_payload(self) -> SimulationPayload:
        """Method to build the payload for the simulation"""
        if self._arrivals is None:
            msg = "The arrivals generator must be instantiated before the simulation"
            raise ValueError(msg)
        if self._client is None:
            msg = "The client input must be instantiated before the simulation"
            raise ValueError(msg)
        if not self._servers:
            msg = "You must instantiate at least one server before the simulation"
            raise ValueError(msg)
        if self._edges_kind is None:
            msg = "You must instantiate edges before the simulation."
            raise ValueError(msg)

        # mypy facilitator
        edges_u: list[NetworkEdge] | list[LinkEdge]
        if self._edges_kind == SystemEdges.NETWORK_CONNECTION:
            if not self._net_edges:
                msg = "You must instantiate edges before the simulation."
                raise ValueError(msg)
            edges_u = self._net_edges
        else:
            if not self._link_edges:
                msg = "You must instantiate edges before the simulation."
                raise ValueError(msg)
            edges_u = self._link_edges

        if self._sim_settings is None:
            msg = "The simulation settings must be instantiated before the simulation"
            raise ValueError(msg)

        nodes = TopologyNodes(
            servers=self._servers,
            client=self._client,
            load_balancer=self._load_balancer,
        )

        graph = TopologyGraph(
            nodes = nodes,
            edges=edges_u,
        )

        return SimulationPayload.model_validate({
            "arrivals": self._arrivals,
            "topology_graph": graph,
            "sim_settings": self._sim_settings,
            "events": self._events or None,
        })



