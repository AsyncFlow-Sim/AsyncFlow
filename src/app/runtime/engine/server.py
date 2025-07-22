"""
definition of the class necessary to manage the server
during the simulation
"""

from collections.abc import Generator
from typing import TYPE_CHECKING

import numpy as np
import simpy

from app.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    StepOperation,
    SystemNodes,
)
from app.runtime.engine.edge import EdgeRuntime
from app.runtime.types import ServerContainers, ServerResourceName
from app.schemas.system_topology_schema.full_system_topology_schema import Server

if TYPE_CHECKING:
    from app.runtime.rqs_state import RequestState


class ServerRuntime:
    """class to define the server during the simulation"""

    def __init__(  # noqa: PLR0913
        self,
        env: simpy.Environment,
        server_resources: ServerContainers,
        server_config: Server,
        out_edge: EdgeRuntime,
        server_box: simpy.Store,
        rng: np.random.Generator | None = None,
    ) -> None:
        """Server attributes

        Args:
            env (simpy.Environment): _description_
            server_resources (ServerContainers): _description_
            server_config (Server): _description_
            out_edge (EdgeRuntime): _description_
            server_box (simpy.Store): _description_
            rng (np.random.Generator | None, optional): _description_. Defaults to None.

        """
        self.env = env
        self.server_resources = server_resources
        self.server_config = server_config
        self.out_edge = out_edge
        self.server_box = server_box
        self.rng = rng or np.random.default_rng()


    def _forwarder(self) -> Generator[simpy.Event, None, None]:
        """
        Define all the step each request has to do ones reach
        the server
        """
        # Define the length of the endpoint list
        endpoints_list = self.server_config.endpoints
        endpoints_number = len(endpoints_list)


        while True:
            state: RequestState = yield self.server_box.get() # type: ignore[assignment]

            #register the history for the state:
            state.record_hop(
                SystemNodes.SERVER,
                self.server_config.id,
                self.env.now,
            )
            # select the endpoint where the requests is directed at the moment we use
            # a uniform distribution, in the future we will allow the user to define a
            # custom distribution
            selected_endpoint_idx = self.rng.integers(low=0, high=endpoints_number)
            selected_endpoint = endpoints_list[selected_endpoint_idx]

            # RAM management:
            # first calculate the ram needed
            # Ask if it is available
            # Release everything when the operation completed

            total_ram = sum(
                step.step_operation[StepOperation.NECESSARY_RAM]
                for step in selected_endpoint.steps
                if isinstance(step.kind, EndpointStepRAM)
            )

            # 4) prenoto quella RAM TUTTA INSIEME
            if total_ram:
                yield self.server_resources[ServerResourceName.RAM.value].get(total_ram)


            for step in selected_endpoint.steps:
                if isinstance(step.kind, EndpointStepCPU):

                    # operation do not continue until the core is busy
                    yield self.server_resources[ServerResourceName.CPU.value].get(1)

                    # in a cpu bound task we wait the necessary time keeping the core
                    # busy to simulate the fact that the event loop cannot elaborate
                    # another task
                    cpu_time = step.step_operation[StepOperation.CPU_TIME]
                    yield self.env.timeout(cpu_time)

                    # the core is again free
                    yield self.server_resources[ServerResourceName.CPU.value].put(1)

                elif isinstance(step.kind, EndpointStepIO):
                    # here we do not require the core to be busy to simulate
                    # the fact that other requests to the endpoint can be elaborated
                    # in the event loop in a I/O operation
                    yield self.env.timeout(
                        step.step_operation[StepOperation.IO_WAITING_TIME],
                    )

            # release the ram
            if total_ram:
                yield self.server_resources[ServerResourceName.RAM.value].put(total_ram)

            self.out_edge.transport(state)



    def server_runtime(self) -> simpy.Process:
        """Generate the process to simulate the server inside simpy env"""
        return self.env.process(self._forwarder())

