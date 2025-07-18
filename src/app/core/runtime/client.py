"""defining the object client for the simulation"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import simpy

from app.config.constants import SystemNodes
from app.core.runtime.edge import EdgeRuntime
from app.schemas.system_topology_schema.full_system_topology_schema import Client

if TYPE_CHECKING:
    from app.config.rqs_state import RequestState



class ClientRuntime:
    """class to define the client runtime"""

    def __init__(
        self,
        env: simpy.Environment,
        out_edge: EdgeRuntime,
        client_box: simpy.Store,
        completed_box: simpy.Store,
        client_config: Client,
        ) -> None:
        """Definition of attributes for the client"""
        self.env = env
        self.out_edge = out_edge
        self.client_config = client_config
        self.client_box = client_box
        self.completed_box = completed_box


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        while True:
            state: RequestState = yield self.client_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.CLIENT,
                    self.client_config.id,
                    self.env.now,
                )

            # by checking the previous node (-2 the previous component is an edge)
            # we are able to understand if the request should be elaborated
            # when the type is Generator, or the request is completed, in this case
            # the client is the target and the previous node type is not a rqs generator
            if state.history[-2].component_type != SystemNodes.GENERATOR:
                state.finish_time = self.env.now
                yield self.completed_box.put(state)
            else:
                self.out_edge.transport(state)

    def client_run(self) -> simpy.Process:
        """Initialization of the process"""
        return self.env.process(self._forwarder())
