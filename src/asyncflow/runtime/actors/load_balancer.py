"""Definition of the node represented by the LB in the simulation"""


from collections import OrderedDict
from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, cast

import simpy

from asyncflow.config.enums import LbAlgorithmsName, SystemNodes
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.actors.routing.lb_algorithms import (
    LB_TABLE,
)
from asyncflow.schemas.topology.nodes import LoadBalancer

if TYPE_CHECKING:
    from asyncflow.runtime.rqs_state import RequestState



class LoadBalancerRuntime:
    """class to define the behaviour of the LB in the simulation"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        lb_config: LoadBalancer,

        # We use an OrderedDict because, for the RR algorithm,
        # we rotate elements in O(1) by moving the selected key to the end.
        # An OrderedDict also lets us remove an element by key in O(1)
        # without implementing a custom doubly linked list + hashmap.
        # Keys are the unique edge IDs that connect the LB to the servers.
        # If multiple LBs are present, the SimulationRunner assigns
        # the correct dict to each LB. Removals/insertions are performed
        # by the EventInjectionRuntime.

        lb_out_edges: OrderedDict[str, EdgeRuntime],
        lb_box: simpy.Store,
    ) -> None:
        """
        Descriprion of the instance attributes for the class
        Args:
            env (simpy.Environment): Simulation environment.
            lb_config (LoadBalancer): LB configuration for the runtime.
            out_edges (OrderedDict[str, EdgeRuntime]): Edges connecting
            the LB to servers.
            lb_box (simpy.Store): Queue (mailbox) from which the LB
            consumes request states.
        """
        self.env = env
        self.lb_config = lb_config
        self.lb_out_edges = lb_out_edges
        self.lb_box = lb_box

        # FIFO of free edges connecting to ready servers
        self._free_edges = simpy.Store(env)

        # Global collection of LB waiting times (FCFS only).
        # We store one value per request that actually waited at the LB.
        # This is aggregate-only: we do NOT track per-request IDs here.
        # We need it to compare simulated and theoretical results of
        # queue theory
        self._lb_waiting_time: list[float] = []


    # Helpers FCFS

    def on_edge_added(self, edge_id: str) -> None:
        """
        Called when EventInjection re-enables an edge.
        We push one token so the edge becomes immediately eligible.
        """
        if edge_id in self.lb_out_edges:
            self._free_edges.put(edge_id)


    def _prime_free_edges(self) -> None:
        """Prepare initial edges in the FIFO"""
        for edge_id in self.lb_out_edges:
            self._free_edges.put(edge_id)


    def mark_free(self, edge_id: str) -> None:
        """
        Put the token if and only if the edges is still
        available, the event injection might remove temporary
        a server by removing its connection with the LB
        """
        if edge_id in self.lb_out_edges:
            self._free_edges.put(edge_id)


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        while True:
            state: RequestState = yield self.lb_box.get()  # type: ignore[assignment]

            if self.lb_config.algorithms == LbAlgorithmsName.FCFS:

                hist = getattr(state, "history", None)
                if hist:
                    last = hist[-1]
                    t_arrival = getattr(last, "timestamp", float(self.env.now))
                else:
                    t_arrival = float(self.env.now)


                state.record_hop(
                        SystemNodes.LOAD_BALANCER,
                        self.lb_config.id,
                        self.env.now,
                    )

            # The idea is the following: when a request arrives and the algorithm
            # is FCFS, we maintain a FIFO of available edges. If an edge connected
            # to a server is ready, the loop continues and (assuming no event injection
            # has removed the server) the waiting time should be 0. If no edge is
            # available, the request waits until the server notifies the LB via the
            # `mark_free` callback. At that point, the edge is released and we can
            # compute the waiting time.
            #
            # The check on the OrderedDict is important because an event injection
            # may temporarily remove a server by cutting its edge from the load
            # balancer. In such cases, the loop restarts until a valid edge is found.

                while True:
                    edge_id = cast("str", (yield self._free_edges.get()))
                    # if event injection remove the edge,
                    # discard the token and wait
                    if edge_id in self.lb_out_edges:
                        break
                    # token stale → loop and take the next

                waiting_time = self.env.now - t_arrival
                if waiting_time >= 0:
                    self._lb_waiting_time.append(waiting_time)

                edge_rt = self.lb_out_edges[edge_id]
                edge_rt.transport(state)
            else:
                state.record_hop(
                SystemNodes.LOAD_BALANCER,
                self.lb_config.id,
                self.env.now,
            )
                edge_rt = LB_TABLE[self.lb_config.algorithms](self.lb_out_edges)
                edge_rt.transport(state)

    def start(self) -> simpy.Process:
        """Start the process and populate FIFO"""
        self._prime_free_edges()
        return self.env.process(self._forwarder())

    @property
    def lb_waiting_times(self) -> Sequence[float]:
        """Read-only view of LB FCFS waiting times (one per waited request)."""
        return tuple(self._lb_waiting_time)
