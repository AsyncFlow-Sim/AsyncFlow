"""Definition of the node represented by the LB in the simulation"""


from collections import OrderedDict, defaultdict
from collections.abc import Generator
from typing import (
    TYPE_CHECKING,
)

import simpy

from asyncflow.config.enums import LbAlgorithmsName, SystemNodes
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.actors.routing.lb_algorithms import (
    LB_TABLE,
    fcfs_picker,
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

        # we need to keep track of the server that are busy
        # right now we don't have multiprocess so each server has
        # one core, to handle multiprocess in the feature we would
        # have to add a new structure called capacity
        self._busy: dict[str, int] = defaultdict(int)

        # In the case of a FCFS algo or similar if no servers
        # are available we need to wait before starting the algo
        self._wait_ev: simpy.Event | None = None

    # Helpers FCFS
    # We manage here the logic for this algo because we need to be carefull
    # to dont have collision with eventinjectionruntime, that's why we are
    # not popping and rotating from the ordered dict with key edge_id and
    # value edge runtime, but we manage adding an extra structure to know
    # the state of the servers through the edges connecting them with the LB
    def mark_busy(self, edge_id: str) -> None:
        """Helper to manage the state of the available server"""
        self._busy[edge_id] += 1

    def mark_free(self, edge_id: str) -> None:
        """Helper to manage the state of the available server"""
        b = self._busy.get(edge_id, 0)
        if b > 0:
            self._busy[edge_id] = b - 1
        if self._wait_ev is not None and not self._wait_ev.triggered:
            self._wait_ev.succeed()

    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        while True:
            state: RequestState = yield self.lb_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.LOAD_BALANCER,
                    self.lb_config.id,
                    self.env.now,
                )

            if self.lb_config.algorithms == LbAlgorithmsName.FCFS:
                # FCFS: wait for an edge to be free
                pick = fcfs_picker(self.lb_out_edges, self._busy)
                while pick is None:
                    if self._wait_ev is None or self._wait_ev.triggered:
                        self._wait_ev = self.env.event()
                    yield self._wait_ev
                    pick = fcfs_picker(self.lb_out_edges, self._busy)

                edge_id, edge_rt = pick
                # mark the server as occupied
                self.mark_busy(edge_id)
                # transport the request
                edge_rt.transport(state)
            else:
                # Algo different from FCFS
                edge_rt = LB_TABLE[self.lb_config.algorithms](self.lb_out_edges)
                edge_rt.transport(state)

    def start(self) -> simpy.Process:
        """Initialization of the simpy process for the LB"""
        return self.env.process(self._forwarder())
