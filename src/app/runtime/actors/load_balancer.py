"""Definition of the node represented by the LB in the simulation"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import simpy

from app.config.constants import LbAlgorithmsName, SystemNodes
from app.runtime.actors.edge import EdgeRuntime
from app.runtime.actors.helpers.lb_algorithms import (
    least_connections,
    round_robin,
)
from app.schemas.system_topology.full_system_topology import LoadBalancer

if TYPE_CHECKING:
    from app.runtime.rqs_state import RequestState



class LoadBalancerRuntime:
    """class to define the behaviour of the LB in the simulation"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        lb_config: LoadBalancer,
        outer_edges: list[EdgeRuntime],
        lb_box: simpy.Store,
    ) -> None:
        """
        Descriprion of the instance attributes for the class
        Args:
            env (simpy.Environment): env of the simulation
            lb_config (LoadBalancer): input to define the lb in the runtime
            rqs_state (RequestState): state of the simulation
            outer_edges (list[EdgeRuntime]): list of edges that connects lb with servers
            lb_box (simpy.Store): store to add the state

        """
        self.env = env
        self.lb_config = lb_config
        self.outer_edges = outer_edges
        self.lb_box = lb_box
        self._round_robin_index: int = 0


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        while True:
            state: RequestState = yield self.lb_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.LOAD_BALANCER,
                    self.lb_config.id,
                    self.env.now,
                )

            if self.lb_config.algorithms == LbAlgorithmsName.ROUND_ROBIN:
                outer_edge, self._round_robin_index = round_robin(
                    self.outer_edges,
                    self._round_robin_index,
                )
            else:
                outer_edge = least_connections(self.outer_edges)

            outer_edge.transport(state)

    def start(self) -> simpy.Process:
        """Initialization of the simpy process for the LB"""
        return self.env.process(self._forwarder())
