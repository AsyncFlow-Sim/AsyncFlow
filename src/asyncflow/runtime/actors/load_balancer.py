"""Definition of the node represented by the LB in the simulation"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import simpy

from asyncflow.config.constants import LbAlgorithmsName, SystemNodes
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.actors.routing.lb_algorithms import (
    least_connections,
    round_robin,
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
        out_edges: list[EdgeRuntime] | None,
        lb_box: simpy.Store,
    ) -> None:
        """
        Descriprion of the instance attributes for the class
        Args:
            env (simpy.Environment): env of the simulation
            lb_config (LoadBalancer): input to define the lb in the runtime
            rqs_state (RequestState): state of the simulation
            out_edges (list[EdgeRuntime]): list of edges that connects lb with servers
            lb_box (simpy.Store): store to add the state

        """
        self.env = env
        self.lb_config = lb_config
        self.out_edges = out_edges
        self.lb_box = lb_box
        self._round_robin_index: int = 0


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        assert self.out_edges is not None
        while True:
            state: RequestState = yield self.lb_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.LOAD_BALANCER,
                    self.lb_config.id,
                    self.env.now,
                )

            if self.lb_config.algorithms == LbAlgorithmsName.ROUND_ROBIN:
                out_edge, self._round_robin_index = round_robin(
                    self.out_edges,
                    self._round_robin_index,
                )
            else:
                out_edge = least_connections(self.out_edges)

            out_edge.transport(state)

    def start(self) -> simpy.Process:
        """Initialization of the simpy process for the LB"""
        return self.env.process(self._forwarder())
