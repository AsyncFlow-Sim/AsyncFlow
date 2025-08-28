"""
definition of the class necessary to manage the server
during the simulation
"""

from collections.abc import Generator
from typing import cast

import numpy as np
import simpy

from asyncflow.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    SampledMetricName,
    ServerResourceName,
    StepOperation,
    SystemNodes,
)
from asyncflow.metrics.server import build_server_metrics
from asyncflow.resources.server_containers import ServerContainers
from asyncflow.runtime.actors.edge import EdgeRuntime
from asyncflow.runtime.rqs_state import RequestState
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.nodes import Server


class ServerRuntime:
    """class to define the server during the simulation"""

    def __init__( # noqa: PLR0913
        self,
        *,
        env: simpy.Environment,
        server_resources: ServerContainers,
        server_config: Server,
        out_edge: EdgeRuntime | None,
        server_box: simpy.Store,
        settings: SimulationSettings,
        rng: np.random.Generator | None = None,
        ) -> None:
        """
        Definition of the instance attributes
        Args:
            env (simpy.Environment): simpy environment
            server_resources (ServerContainers):resource defined in the
                input for each server
            server_config (Server): parameter to define the server from the input
            out_edge (EdgeRuntime): edge connecting the server to the next node
            server_box (simpy.Store): box with the states that the server
                should elaborate
            settings (SimulationSettings): general input settings for the simulation
            rng (np.random.Generator | None, optional): random number generator.
        """
        self.env = env
        self.server_resources = server_resources
        self.server_config = server_config
        self.out_edge = out_edge
        self.server_box = server_box
        self.rng = rng or np.random.default_rng()
        # length of the active queue of the event loop
        self._el_ready_queue_len: int = 0
        # total ram used in the server
        self._ram_in_use: int | float = 0
        # length of the queue of the I/O task of the vent loop
        self._el_io_queue_len: int = 0

        # Right now is not necessary but as we will introduce
        # non mandatory metrics we will need this structure to
        # check if we have to measure a given metric
        # right now it is not necessary because we are dealing
        # only with mandatory metrics
        self._server_enabled_metrics = build_server_metrics(
            settings.enabled_sample_metrics,
        )

    # right now we disable the warnings but a refactor will be done soon
    def _handle_request( # noqa: PLR0915, PLR0912, C901
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


        # Extract the total ram to execute the endpoint
        total_ram = sum(
            step.step_operation[StepOperation.NECESSARY_RAM]
            for step in selected_endpoint.steps
            if isinstance(step.kind, EndpointStepRAM)
        )

        # ------------------------------------------------------------------
        # CPU & RAM SCHEDULING
        #
        #  RAM FIRST, CPU LATER
        #   - The request reserves its full working set (total_ram) BEFORE
        #     trying to acquire a CPU core. If memory is not available, the
        #     request blocks on RAM and never enters the CPU/ready flow.
        #
        #  LAZY CPU-LOCK (CPU bursts)
        #   - A CPU token is acquired only at the FIRST CPU step of a burst
        #     (`if not core_locked`). Consecutive CPU steps reuse the same token.
        #   - As soon as an I/O step is encountered, the token is released
        #     (`CPU.put(1)`) and remains free until the next CPU step.
        #
        #  READY QUEUE (new definition)
        #   - The ready queue tracks ONLY requests waiting for a core.
        #   - Increment ready when `CPU.get(1)` is NOT immediately satisfied
        #     (`event.triggered == False`).
        #   - Decrement ready right after the `yield cpu_req` succeeds,
        #     i.e. when the core is actually granted.
        #   - A request currently executing on a core (`core_locked=True`)
        #     is NOT counted in ready.
        #
        #  WHY THIS IS REALISTIC
        #   - Prevents “core-hogging” during long I/O waits (the core is released).
        #   - Avoids redundant get/put calls on consecutive CPU steps.
        #   - Mirrors a real async server: a worker thread/GIL is held only
        #     during CPU-bound code and released on each `await` (I/O).
        #
        #  END OF HANDLER
        #   - If the request still holds a core at the end, release it.
        #   - Then release the reserved RAM.
        # ------------------------------------------------------------------

        # Ask the necessary ram to the server
        if total_ram:
            yield self.server_resources[ServerResourceName.RAM.value].get(total_ram)
            self._ram_in_use += total_ram


        # Initial conditions of the server: a rqs a priori is not in any queue
        # and it does not occupy a core until it started to be elaborated
        # these are local variable so they are created for every request.
        core_locked = False
        is_in_io_queue = False
        waiting_cpu = False


        # --- Step Execution: CPU & I/O dynamics ---
        #
        #  EDGE CASE: First-step I/O
        #   - An endpoint can start with an I/O step: in that case the request
        #     holds no core (`core_locked=False`) and enters the I/O queue.
        #     Ready queue is unaffected. This is not realistic since the first
        #     step is usually related to the parsing of the requests however
        #     we prevent this case, since right now we dont have a pydantic
        #     validation to ensure the first step is CPU bounderd
        #
        #  Consecutive I/O steps
        #   - The second (and later) I/O step sees is_in_io_queue=True, so it
        #     does NOT increment again → no double-counting in I/O.
        #
        #  Transition CPU → I/O → CPU (with new ready semantics)
        #   - CPU step:
        #       * If no core is held, create cpu_req = CPU.get(1).
        #       * If cpu_req.triggered == False → the request is waiting → ready += 1.
        #       * After yield cpu_req (core granted) → ready -= 1, set core_locked=True.
        #       * A request currently executing on a core is NOT in ready.
        #   - I/O step:
        #       * If holding a core, release it (`CPU.put(1)`) and enter I/O queue (+1).
        #       * If already in I/O (consecutive step), do nothing (no double-counting).
        #       * Ready queue is never touched here.
        #   - Next CPU step:
        #       * Leave I/O queue (if counted) and repeat CPU acquisition logic.
        #       * If acquisition is not immediate, enter ready until the event resolves.
        #
        #  Endpoint completion
        #   - If core_locked=True → release the core.
        #   - If is_in_io_queue=True → leave the I/O queue.
        #   - waiting_cpu should be False by now; if not, remove from ready defensively.
        #   - Invariant: the request must not remain counted in any queue once finished.
        # -------------------------------------------------------------------



        for step in selected_endpoint.steps:

            if step.kind in EndpointStepCPU:
                # with the boolean we avoid redundant operation of asking
                # the core multiple time on a given step
                # for example if we have two consecutive cpu bound step
                # in this configuration we are asking the cpu just in the
                # first one

                if is_in_io_queue:
                    is_in_io_queue = False
                    self._el_io_queue_len -= 1

                if not core_locked:
                    # simpy create an event and if it can be satisfied is triggered
                    cpu_req = self.server_resources[ServerResourceName.CPU.value].get(1)

                    # no trigger ready queue without execution
                    if not cpu_req.triggered:
                        waiting_cpu = True
                        self._el_ready_queue_len += 1

                    # at this point wait for the cpu
                    yield cpu_req

                    # here the cpu is free
                    if waiting_cpu:
                        waiting_cpu = False
                        self._el_ready_queue_len -= 1

                    core_locked = True

                cpu_time = step.step_operation[StepOperation.CPU_TIME]
                # Execute the step giving back the control to the simpy env
                yield self.env.timeout(cpu_time)

            # since the object is of an Enum class we check if the step.kind
            # is one member of enum
            elif step.kind in EndpointStepIO:
                # define the io time
                io_time = step.step_operation[StepOperation.IO_WAITING_TIME]

                if core_locked:
                    # release the core coming from a cpu step
                    yield self.server_resources[ServerResourceName.CPU.value].put(1)
                    core_locked = False

                    if not is_in_io_queue:
                        is_in_io_queue = True
                        self._el_io_queue_len += 1
                elif not is_in_io_queue:
                    is_in_io_queue = True
                    self._el_io_queue_len += 1

                yield self.env.timeout(io_time)

        if core_locked:
            yield self.server_resources[ServerResourceName.CPU.value].put(1)
            core_locked = False

        if is_in_io_queue:
            is_in_io_queue = False
            self._el_io_queue_len -= 1

        if waiting_cpu:
            waiting_cpu = False
            self._el_ready_queue_len -= 1


        if total_ram:

            self._ram_in_use -= total_ram
            yield self.server_resources[ServerResourceName.RAM.value].put(total_ram)

        assert self.out_edge is not None
        self.out_edge.transport(state)


    # we need three accessor because we need to read these private attribute
    # in the sampled metric collector
    @property
    def ready_queue_len(self) -> int:
        """Current length of the event-loop ready queue for this server."""
        return self._el_ready_queue_len

    @property
    def io_queue_len(self) -> int:
        """Current length of the event-loop I/O queue for this server."""
        return self._el_io_queue_len

    @property
    def ram_in_use(self) -> int | float:
        """Total RAM (MB) currently reserved by active requests."""
        return self._ram_in_use

    @property
    def enabled_metrics(self) -> dict[SampledMetricName, list[float | int]]:
        """Read-only access to the metric store."""
        return self._server_enabled_metrics



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

