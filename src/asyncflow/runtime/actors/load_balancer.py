"""Definition of the node represented by the LB in the simulation"""


from collections import OrderedDict
from collections.abc import Generator
from typing import (
    TYPE_CHECKING,
)

import simpy

from asyncflow.config.constants import SystemNodes
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.actors.routing.lb_algorithms import LB_TABLE
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



    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        while True:
            state: RequestState = yield self.lb_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.LOAD_BALANCER,
                    self.lb_config.id,
                    self.env.now,
                )

            out_edge = LB_TABLE[self.lb_config.algorithms](self.lb_out_edges)
            out_edge.transport(state)

    def start(self) -> simpy.Process:
        """Initialization of the simpy process for the LB"""
        return self.env.process(self._forwarder())
