"""
definition of the class necessary to manage the server
during the simulation
"""

from collections.abc import Generator
from typing import cast

import numpy as np
import simpy

from app.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    ServerResourceName,
    StepOperation,
    SystemNodes,
)
from app.resources.server_containers import ServerContainers
from app.runtime.actors.edge import EdgeRuntime
from app.runtime.rqs_state import RequestState
from app.schemas.system_topology.full_system_topology import Server


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


    def _handle_request(
        self,
        state: RequestState,
        ) -> Generator[simpy.Event, None, None]:
        """
        Define all the step each request has to do ones reach
        the server
        """
        #register the history for the state:
        state.record_hop(
            SystemNodes.SERVER,
            self.server_config.id,
            self.env.now,
        )

        # Define the length of the endpoint list
        endpoints_list = self.server_config.endpoints
        endpoints_number = len(endpoints_list)

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


        if total_ram:
            yield self.server_resources[ServerResourceName.RAM.value].get(total_ram)


        # --- Step Execution: Process CPU and IO operations ---
        for step in selected_endpoint.steps:

            if isinstance(step.kind, EndpointStepCPU):
                cpu_time = step.step_operation[StepOperation.CPU_TIME]

                # Acquire one core
                yield self.server_resources[ServerResourceName.CPU.value].get(1)
                # Hold the core busy
                yield self.env.timeout(cpu_time)
                # Release the core
                yield self.server_resources[ServerResourceName.CPU.value].put(1)

            elif isinstance(step.kind, EndpointStepIO):
                io_time = step.step_operation[StepOperation.IO_WAITING_TIME]
                yield self.env.timeout(io_time)  # Wait without holding a CPU core

        # release the ram
        if total_ram:
            yield self.server_resources[ServerResourceName.RAM.value].put(total_ram)

        self.out_edge.transport(state)

    def _dispatcher(self) -> Generator[simpy.Event, None, None]:
        """
        The main dispatcher loop. It pulls requests from the inbox and
        spawns a new '_handle_request' process for each one.
        """
        while True:
            # Wait for a request to arrive in the server's inbox
            raw_state = yield self.server_box.get()
            request_state = cast("RequestState", raw_state)
            # Spawn a new, independent process to handle this request
            self.env.process(self._handle_request(request_state))

    def start(self) -> simpy.Process:
        """Generate the process to simulate the server inside simpy env"""
        return self.env.process(self._dispatcher())

