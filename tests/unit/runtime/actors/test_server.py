"""Unit-tests for ServerRuntime concurrency, resource handling and metrics.

Each test spins up an isolated SimPy environment containing:

* one ServerRuntime
* one mock edge with zero-latency delivery (InstantEdge)
* an inbox (simpy.Store) for incoming requests
* a sink (simpy.Store) that receives the request after the server

The server exposes:
  RAM = 1024 MB,  CPU cores = 2
and a single endpoint with the step sequence:
  RAM(128 MB) ➜ CPU(5 ms) ➜ I/O(20 ms).

All timings are in **seconds** because SimPy's clock is unit-agnostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import simpy
from numpy.random import default_rng

from asyncflow.config.constants import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    SampledMetricName,
    StepOperation,
)
from asyncflow.resources.server_containers import build_containers
from asyncflow.runtime.actors.server import ServerRuntime
from asyncflow.runtime.rqs_state import RequestState
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.endpoint import Endpoint, Step
from asyncflow.schemas.topology.nodes import (
    Server,
    ServerResources,
)

if TYPE_CHECKING:

    from collections.abc import Generator



# ---------------------------------------------------------------------------#
# Helpers                                                                    #
# ---------------------------------------------------------------------------#
class InstantEdge:
    """Stub EdgeRuntime with zero latency and no drops."""

    def __init__(self, env: simpy.Environment, sink: simpy.Store) -> None:
        """Attribute"""
        self._env = env
        self._sink = sink

    def transport(self, state: RequestState) -> simpy.Process:
        """Transport function"""
        return self._env.process(self._deliver(state))

    def _deliver(self, state: RequestState) -> Generator[simpy.Event, None, None]:
        """Deliver function"""
        yield self._sink.put(state)


def _make_server_runtime(
    env: simpy.Environment,
) -> tuple[ServerRuntime, simpy.Store]:
    """Return a (ServerRuntime, sink) ready for injection tests."""
    # Resources
    res_spec = ServerResources(cpu_cores=2, ram_mb=1024)
    containers = build_containers(env, res_spec)

    # Endpoint: RAM → CPU → I/O
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

    server_cfg = Server(id="api_srv", endpoints=[endpoint], server_resources=res_spec)

    inbox: simpy.Store = simpy.Store(env)
    sink: simpy.Store = simpy.Store(env)
    edge = InstantEdge(env, sink)

    settings = SimulationSettings(total_simulation_time=1900, sample_period_s=0.1)

    runtime = ServerRuntime(
        env=env,
        server_resources=containers,
        server_config=server_cfg,
        out_edge=edge,          # type: ignore[arg-type]
        server_box=inbox,
        settings=settings,
        rng=default_rng(seed=0),
    )
    return runtime, sink


# ---------------------------------------------------------------------------#
# Tests                                                                      #
# ---------------------------------------------------------------------------#
def test_ram_is_released_at_end() -> None:
    """RAM tokens must return to capacity once the request finishes."""
    env = simpy.Environment()
    server, sink = _make_server_runtime(env)

    server.server_box.put(RequestState(id=1, initial_time=0.0))
    server.start()
    env.run()

    ram = server.server_resources["RAM"]
    assert ram.level == ram.capacity
    assert len(sink.items) == 1


def test_cpu_core_held_only_during_cpu_step() -> None:
    """Exactly one core is busy during the CPU-bound window (0 5ms)."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env)
    cpu = server.server_resources["CPU"]

    server.server_box.put(RequestState(id=2, initial_time=0.0))
    server.start()

    env.run(until=0.004)  # mid-CPU step
    assert cpu.level == 1  # 2-1

    env.run(until=0.006)  # after CPU step
    assert cpu.level == 2  # released


def test_ready_and_io_queue_counters() -> None:
    """ready_queue_len and io_queue_len should toggle as CPU⇄I/O phases alternate."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env)

    server.server_box.put(RequestState(id=3, initial_time=0.0))
    server.start()

    # 1) before start queues are empty
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0

    # 2) during CPU (0 5ms) ready queue+1
    env.run(until=0.003)
    assert server.ready_queue_len == 1
    assert server.io_queue_len == 0

    # 3) during I/O (5 25ms) ready 0, io+1
    env.run(until=0.010)
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 1

    # 4) completed both back to 0
    env.run()
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0


def test_enabled_metrics_dict_populated() -> None:
    """ServerRuntime must create lists for every mandatory sampled metric."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env)

    mandatory = {
        SampledMetricName.RAM_IN_USE,
        SampledMetricName.READY_QUEUE_LEN,
        SampledMetricName.EVENT_LOOP_IO_SLEEP,
    }
    assert mandatory.issubset(server.enabled_metrics.keys())
