"""Unit tests for the concurrent ServerRuntime.

The tests create an isolated SimPy environment with a test fixture that sets up:
* A single ServerRuntime instance.
* A mock "instant" edge that immediately forwards requests to a sink.
* A server configuration with 2 CPU cores and 1024 MB of RAM.
* A single endpoint with a sequence of RAM, CPU, and I/O steps.

This setup allows for precise testing of resource acquisition/release and
the correct execution of the processing pipeline for a single request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import simpy
from numpy.random import default_rng

from app.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    StepOperation,
    SystemNodes,
)
from app.resources.server_containers import build_containers
from app.runtime.actors.server import ServerRuntime
from app.runtime.rqs_state import RequestState
from app.schemas.system_topology.endpoint import Endpoint, Step
from app.schemas.system_topology.full_system_topology import Server, ServerResources

if TYPE_CHECKING:
    from collections.abc import Generator


# --------------------------------------------------------------------------- #
# Test Helper: A mock edge that instantly delivers requests to a sink.      #
# --------------------------------------------------------------------------- #
class InstantEdge:
    """A test stub for EdgeRuntime with zero latency and no drops.

    This mock allows us to test the ServerRuntime in isolation, without
    introducing the complexities of network simulation.
    """

    def __init__(self, env: simpy.Environment, sink: simpy.Store) -> None:
        """Initializes the mock edge."""
        self.env = env
        self.sink = sink

    def transport(self, state: RequestState) -> simpy.Process:
        """Immediately puts the state in the sink via a SimPy process."""
        return self.env.process(self._deliver(state))

    def _deliver(self, state: RequestState) -> Generator[simpy.Event, None, None]:
        """The generator function that performs the delivery."""
        yield self.sink.put(state)


# --------------------------------------------------------------------------- #
# Test Fixture: Creates a standardized ServerRuntime for tests.             #
# --------------------------------------------------------------------------- #
def _make_server_runtime(
    env: simpy.Environment,
) -> tuple[ServerRuntime, simpy.Store]:
    """Create a ServerRuntime with a dummy edge and return it and the sink store."""
    # 1. Define server resources
    res_spec = ServerResources(cpu_cores=2, ram_mb=1024)
    containers = build_containers(env, res_spec)

    # 2. Define a single endpoint with a sequence of steps
    # Order: RAM (instant) -> CPU (5ms) -> I/O (20ms)
    endpoint = Endpoint(
        endpoint_name="/predict",
        steps=[
            Step(
                kind=EndpointStepRAM.RAM,
                step_operation={StepOperation.NECESSARY_RAM: 128},
            ),
            Step(
                kind=EndpointStepCPU.CPU_BOUND_OPERATION,
                step_operation={StepOperation.CPU_TIME: 0.005},
            ),
            Step(
                kind=EndpointStepIO.DB,
                step_operation={StepOperation.IO_WAITING_TIME: 0.020},
            ),
        ],
    )

    # 3. Create the full server configuration
    server_cfg = Server(
        id="api_srv",
        endpoints=[endpoint],
        server_resources=res_spec,
    )

    # 4. Set up the simulation environment with mock components
    inbox: simpy.Store = simpy.Store(env)
    sink: simpy.Store = simpy.Store(env)
    edge = InstantEdge(env, sink)

    # 5. Instantiate the ServerRuntime
    runtime = ServerRuntime(
        env=env,
        server_resources=containers,
        server_config=server_cfg,
        out_edge=edge,  # type: ignore[arg-type]
        server_box=inbox,
        rng=default_rng(0),
    )
    return runtime, sink


# --------------------------------------------------------------------------- #
# Unit Tests                                                                  #
# --------------------------------------------------------------------------- #
def test_server_reserves_and_releases_ram() -> None:
    """Verify that RAM is acquired at the start and fully released at the end."""
    env = simpy.Environment()
    server, sink = _make_server_runtime(env)

    # Prepare a request and inject it into the server's inbox.
    req = RequestState(id=1, initial_time=0.0)
    server.server_box.put(req)

    # Start the server's dispatcher process and run until all events are processed.
    server.start()
    env.run()

    ram_container = server.server_resources["RAM"]
    # After the request is fully processed, the RAM level must return to its capacity.
    assert ram_container.level == ram_container.capacity, "RAM must be fully released"
    # The request should have successfully reached the sink.
    assert len(sink.items) == 1, "Request should be forwarded to the sink"


def test_cpu_core_held_only_during_cpu_step() -> None:
    """Verify a CPU core is held exclusively during the CPU-bound step."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env)
    cpu_container = server.server_resources["CPU"]

    # Inject a single request and start the server.
    req = RequestState(id=2, initial_time=0.0)
    server.server_box.put(req)
    server.start()

    # The endpoint logic is: RAM (t=0) -> CPU (t=0 to t=0.005).
    # Run the simulation to a point *during* the CPU step.
    env.run(until=0.004)
    # The server has 2 cores. One should be busy.
    assert cpu_container.level == 1, "One core should still be busy during the CPU step"

    # Now, run the simulation past the CPU step's completion.
    env.run(until=0.006)
    # The core should have been released immediately after the CPU step.
    assert cpu_container.level == 2, "Core should be released after the CPU step"


def test_server_records_hop_in_history() -> None:
    """Verify that the request's history correctly records its arrival at the server."""
    env = simpy.Environment()
    server, sink = _make_server_runtime(env)

    # Inject a request and run the simulation to completion.
    req = RequestState(id=3, initial_time=0.0)
    server.server_box.put(req)
    server.start()
    env.run()

    # The request must be in the sink.
    assert len(sink.items) == 1, "Request did not reach the sink"
    finished_req = sink.items[0]

    # Check the request's history for a 'Hop' corresponding to this server.
    assert any(
        hop.component_type == SystemNodes.SERVER and hop.component_id == "api_srv"
        for hop in finished_req.history
    ), "Server hop missing in request history"
