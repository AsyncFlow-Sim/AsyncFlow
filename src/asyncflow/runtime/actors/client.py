"""defining the object client for the simulation"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import simpy

from asyncflow.config.enums import SystemNodes
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.schemas.topology.nodes import Client

if TYPE_CHECKING:
    from asyncflow.runtime.rqs_state import RequestState



class ClientRuntime:
    """class to define the client runtime"""

    def __init__(
        self,
        *,
        env: simpy.Environment,
        out_edge: EdgeRuntime | None,
        client_box: simpy.Store,
        client_config: Client,
        ) -> None:
        """Definition of attributes for the client"""
        self.env = env
        self.out_edge = out_edge
        self.client_config = client_config
        self.client_box = client_box


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """Updtate the state before passing it to another node"""
        assert self.out_edge is not None
        while True:

            state: RequestState = yield self.client_box.get()  # type: ignore[assignment]

            state.record_hop(
                    SystemNodes.CLIENT,
                    self.client_config.id,
                    self.env.now,
                )

            self.out_edge.transport(state)

    def start(self) -> None:
        """Initialization of the process"""
        self.env.process(self._forwarder())

