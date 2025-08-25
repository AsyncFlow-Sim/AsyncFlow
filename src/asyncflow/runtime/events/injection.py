"""
Centralized runtime object to inject events into the simulation.
This covers, for example, deterministic network latency spikes on edges and
scheduled server outages over a defined time window.
"""
from collections import OrderedDict
from collections.abc import Generator
from typing import cast

import simpy

from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.schemas.events.injection import EventInjection
from asyncflow.schemas.topology.edges import Edge
from asyncflow.schemas.topology.nodes import Server

# Helpers to distinguish when the event start and when the event finish
START_MARK = "start"
END_MARK = "end"

# definition of indexes for the tuple to be assigned for the timeline
TIME = 0
EVENT_ID  = 1
TARGET_ID  = 2
START_END = 3

class EventInjectionRuntime:
    """
    Runtime container responsible for applying event effects.
    It ingests validated EventInjection objects plus the current topology
    (edges and servers) and exposes the state needed to activate/deactivate
    event effects during the simulation.
    """

    def __init__(
        self,
        *,
        events: list[EventInjection] | None,
        edges: list[Edge],
        env: simpy.Environment,
        servers: list[Server],
        # This is initiated in the simulation runner to understand
        # the process there are extensive comments in that file
        lb_out_edges: OrderedDict[str, EdgeRuntime],
    ) -> None:
        """
        Definition of the attributes of the instance for
        the object EventInjectionRuntime

        Args:
            events (list[EventInjection]): input data of all events
            edges (list[Edge]): input data for the edges
            env (simpy.Environment): simpy env for the simulation
            servers (list[Server]): input data of the server
            lb_out_edges: OrderedDict[str, EdgeRuntime]:
            ordered dict to handle server events

        """
        self.events = events
        self.edges = edges
        self.env = env
        self.servers = servers
        self.lb_out_edges = lb_out_edges

        # Nested mapping for edge spikes:
        # edges_events: Dict[event_id, Dict[edge_id, float]]
        # The outer key is the globally unique event_id. The inner mapping
        # uses the target edge_id. Because multiple events can apply to the
        # same edge, we use event_id as the primary key. The inner value
        # stores the spike amplitude (in seconds) to apply while the event
        # is active. It is necessary to compute superoposition of spike
        # on the same target

        self._edges_events: dict[str, dict[str, float]] = {}

        # ---------------------------------------------------------
        # THE FOLLOWING TWO INSTANCES ARE THE ONE NECESSARY TO ADD
        # THE SPIKE DURING THE SIMULATION AND THEY WILL BE USED
        # IN THE EDGERUNTIME CLASS
        # ---------------------------------------------------------

        # definition of a dictionary that will be useful in the
        # Edge runtime to track the cumulative spike for a given edge
        # alone, we need this in combination with the above nested map
        # becuase as we said since we allow the superposition of spike
        # we need the nested map to calculate the correct cumulative
        # spike, in this way in the edge runtime we will need just
        # the information of the edge id to have the correct cumulative
        # spike
        # The idea is a nested map to calculate and a suitable dict
        # to be imported in edge runtime that with just the information
        # of the edge id is able to assign the correct delay even
        # with superposition of spike

        self._edges_spike: dict[str, float] = {}

        # We need a set for a fast lookup to determine if a given edge
        # identifid with its own id is affected by an event

        self._edges_affected: set[str] = set()

        # ---------------------------------------------------------------

        # Definition of timeline object, they represent a time
        # ordered list of tuple that we will use to iterate to track
        # and inject the events in the simulation

        self._edges_timeline: list[tuple[float, str, str, str]] = []
        self._servers_timeline: list[tuple[float, str, str, str]] = []

        # No events we do not have to do any operation
        if not self.events:
            return

        # Set for a fast lookup to fill the nested map and
        self._servers_ids = {server.id for server in self.servers}
        self._edges_ids = {edge.id for edge in self.edges}

        for event in self.events:
            start_event = (
                event.start.t_start, event.event_id, event.target_id, START_MARK,
                )
            end_event = (
                event.end.t_end, event.event_id, event.target_id, END_MARK,
                )

            if event.target_id in self._edges_ids:
                spike = event.start.spike_s
                assert spike is not None
                self._edges_events.setdefault(
                    event.event_id,
                    {})[event.target_id] = spike

                self._edges_timeline.append(start_event)
                self._edges_timeline.append(end_event)
                self._edges_affected.add(event.target_id)
            elif event.target_id in self._servers_ids:
                self._servers_timeline.append(start_event)
                self._servers_timeline.append(end_event)

        # Order the two timeline with lambda functions
        self._edges_timeline.sort(
            key=lambda e: (
                e[TIME], e[START_END] == START_MARK, e[EVENT_ID], e[TARGET_ID],
            ),
        )
        self._servers_timeline.sort(
            key=lambda e: (
                e[TIME], e[START_END] == START_MARK, e[EVENT_ID], e[TARGET_ID],
            ),
        )

        # This function is useful to assign to connect the server id
        # that will be down to the edge runtime that we have to remove
        # from the ordered dict

        # Build reverse index: server_id -> (edge_id, EdgeRuntime)
        self._edge_by_server: dict[str, tuple[str, EdgeRuntime]] = {}

        for edge_id, edge_runtime in lb_out_edges.items():
            # Each EdgeRuntime has an associated Edge config.
            # The .edge_config.target corresponds to the server_id.
            server_id = edge_runtime.edge_config.target
            self._edge_by_server[server_id] = (edge_id, edge_runtime)


    def _assign_edges_spike(self) -> Generator[simpy.Event, None, None]:
        """
        Function to manage the assignment of the cumulative spikes
        during the simulation.
        The timeline contains absolute timestamps (seconds since t=0).
        SimPy expects relative waits, so we advance by dt = t_event - last_t.
        After waiting up to the event time, we apply the state change.
        END comes before START at identical timestamps thanks to sorting.
        """
        last_t: float = float(self.env.now)  # usually 0.0 at start

        for event in self._edges_timeline:
            # Explicit type for mypy
            t: float = cast("float", event[TIME])
            event_id: str = cast("str", event[EVENT_ID])
            edge_id: str = cast("str", event[TARGET_ID])
            mark: str = cast("str", event[START_END])

            dt: float = t - last_t
            if dt > 0.0:
                yield self.env.timeout(dt)
            last_t = t

            # Apply the effect at the instant when the event start
            if mark == START_MARK:
                current = self._edges_spike.get(edge_id, 0.0)
                delta = self._edges_events[event_id][edge_id]
                self._edges_spike[edge_id] = current + delta
            else:  # END_MARK
                current = self._edges_spike.get(edge_id, 0.0)
                delta = self._edges_events[event_id][edge_id]
                self._edges_spike[edge_id] = current - delta


    def _assign_server_state(self) -> Generator[simpy.Event, None, None]:
        last_t: float = float(self.env.now)
        for ev in self._servers_timeline:
            t = cast("float", ev[TIME])
            server_id = cast("str", ev[TARGET_ID])
            mark = cast("str", ev[START_END])

            dt = t - last_t
            if dt > 0.0:
                yield self.env.timeout(dt)
            last_t = t

            edge_info = self._edge_by_server.get(server_id)
            if not edge_info:
                continue
            edge_id, edge_runtime = edge_info

            if mark == START_MARK:
                # server DOWN: remove edge from the ordered dict
                self.lb_out_edges.pop(edge_id, None)
            else:
                # server UP: put the edge server lb
                # back in the ordered dict with the
                # policy to move it at the end
                self.lb_out_edges[edge_id] = edge_runtime
                self.lb_out_edges.move_to_end(edge_id)





    def start(self) -> tuple[simpy.Process, simpy.Process]:
        """Start both edge-spike and server-outage timelines."""
        p1 = self.env.process(self._assign_edges_spike())
        p2 = self.env.process(self._assign_server_state())
        return p1, p2

    @property
    def edges_spike(self) -> dict[str, float]:
        """
        Expose the value of the private dict, this will be
        used in the edge runtime to determine the current,
        if exist, network spike
        """
        return self._edges_spike

    @property
    def edges_affected(self) -> set[str]:
        """
        Expose the value of the private set, this will be
        used in the edge runtime to determine the current,
        if exist, network spike
        """
        return self._edges_affected
