"""Unit tests for ServerRuntime concurrency, resources, and metrics.

Each test spins up an isolated SimPy environment with:

* one ServerRuntime
* one mock edge with zero-latency delivery (InstantEdge)
* an inbox (simpy.Store) for incoming requests
* a sink (simpy.Store) receiving the RequestState after the server

Default server:
  RAM = 1024 MB, CPU cores = 2
Default endpoint:
  RAM(128 MB) → CPU(5 ms) → I/O(20 ms)

All timings are in seconds (SimPy is unit-agnostic).
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
from asyncflow.schemas.topology.nodes import Server, ServerResources

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable



# ---------------------------------------------------------------------------#
# Helpers                                                                    #
# ---------------------------------------------------------------------------#


class InstantEdge:
    """Stub EdgeRuntime with zero latency and no drops."""

    def __init__(self, env: simpy.Environment, sink: simpy.Store) -> None:
        """Store environment and sink."""
        self._env = env
        self._sink = sink

    def transport(self, state: RequestState) -> simpy.Process:
        """Schedule the zero-latency delivery."""
        return self._env.process(self._deliver(state))

    def _deliver(
        self, state: RequestState,
    ) -> Generator[simpy.Event, None, None]:
        """Put the state into the sink immediately."""
        yield self._sink.put(state)


def _mk_endpoint(steps: Iterable[Step]) -> Endpoint:
    """Build a single endpoint with the provided steps."""
    return Endpoint(endpoint_name="/predict", steps=list(steps))


def _default_steps() -> tuple[Step, Step, Step]:
    """RAM → CPU → I/O default pipeline."""
    return (
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
    )


def _make_server_runtime(
    env: simpy.Environment,
    *,
    cpu_cores: int = 2,
    ram_mb: int = 1024,
    steps: Iterable[Step] | None = None,
) -> tuple[ServerRuntime, simpy.Store]:
    """Return a (ServerRuntime, sink) ready for injection tests."""
    res_spec = ServerResources(cpu_cores=cpu_cores, ram_mb=ram_mb)
    containers = build_containers(env, res_spec)

    endpoint = _mk_endpoint(steps if steps is not None else _default_steps())
    server_cfg = Server(
        id="api_srv",
        endpoints=[endpoint],
        server_resources=res_spec,
    )

    inbox: simpy.Store = simpy.Store(env)
    sink: simpy.Store = simpy.Store(env)
    edge = InstantEdge(env, sink)

    settings = SimulationSettings(
        total_simulation_time=60,
        sample_period_s=0.01,
    )

    runtime = ServerRuntime(
        env=env,
        server_resources=containers,
        server_config=server_cfg,
        out_edge=edge,  # type: ignore[arg-type]
        server_box=inbox,
        settings=settings,
        rng=default_rng(seed=0),
    )
    return runtime, sink


# ---------------------------------------------------------------------------#
# Tests (ready queue = only requests waiting for a CPU core)                 #
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


def test_cpu_core_held_only_during_cpu_step_single_request() -> None:
    """Single request with 2 cores holds a core only during CPU time."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env, cpu_cores=2)
    cpu = server.server_resources["CPU"]

    server.server_box.put(RequestState(id=2, initial_time=0.0))
    server.start()

    # Mid CPU step (5 ms total).
    env.run(until=0.003)
    # One core in use: level = 2 - 1 = 1
    assert cpu.level == 1
    # No ready-wait, acquisition was immediate.
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0

    # After CPU step, during I/O.
    env.run(until=0.008)
    assert cpu.level == 2  # released
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 1  # now in I/O

    # End.
    env.run()
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0


def test_ready_increases_only_when_cpu_contention_exists() -> None:
    """With 1 core and overlap, the second request waits in ready."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env, cpu_cores=1)

    # First request at t=0.0
    server.server_box.put(RequestState(id=10, initial_time=0.0))
    # Second overlaps during the first CPU window.
    server.server_box.put(RequestState(id=11, initial_time=0.001))

    server.start()

    # During first CPU, second should be in ready.
    env.run(until=0.004)
    assert server.ready_queue_len == 1

    # After first CPU is done, second should start CPU → ready back to 0.
    env.run(until=0.0065)
    assert server.ready_queue_len == 0

    env.run()
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0


def test_consecutive_io_steps_do_not_double_count() -> None:
    """Two consecutive I/O steps count as a single presence in I/O queue."""
    env = simpy.Environment()

    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        Step(
            kind=EndpointStepIO.DB,
            step_operation={StepOperation.IO_WAITING_TIME: 0.010},
        ),
        # Use another valid I/O category (e.g., CACHE) to simulate consecutive I/O.
        Step(
            kind=EndpointStepIO.CACHE,
            step_operation={StepOperation.IO_WAITING_TIME: 0.015},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps)

    server.server_box.put(RequestState(id=20, initial_time=0.0))
    server.start()

    # During first I/O.
    env.run(until=0.005)
    assert server.io_queue_len == 1

    # Still I/O during second consecutive I/O step; stays 1.
    env.run(until=0.020)
    assert server.io_queue_len == 1

    env.run()
    assert server.io_queue_len == 0
    assert server.ready_queue_len == 0


def test_first_step_io_enters_io_queue_without_touching_ready() -> None:
    """First-step I/O enters I/O queue and leaves ready untouched."""
    env = simpy.Environment()

    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        # Valid I/O category for first-step I/O (e.g., WAIT).
        Step(
            kind=EndpointStepIO.WAIT,
            step_operation={StepOperation.IO_WAITING_TIME: 0.010},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: 0.005},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps, cpu_cores=1)

    server.server_box.put(RequestState(id=30, initial_time=0.0))
    server.start()

    # During first I/O window.
    env.run(until=0.005)
    assert server.io_queue_len == 1
    assert server.ready_queue_len == 0

    # When switching to CPU: with a single request, acquisition is immediate.
    env.run(until=0.012)
    assert server.ready_queue_len == 0

    env.run()
    assert server.io_queue_len == 0
    assert server.ready_queue_len == 0


def test_cpu_burst_reuses_single_token_no_extra_ready() -> None:
    """Consecutive CPU steps reuse the same token; no extra ready bumps."""
    env = simpy.Environment()

    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: 0.004},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: 0.004},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps, cpu_cores=1)
    cpu = server.server_resources["CPU"]

    server.server_box.put(RequestState(id=40, initial_time=0.0))
    server.start()

    # During first CPU step.
    env.run(until=0.002)
    assert cpu.level == 0  # 1 core total, 1 in use
    assert server.ready_queue_len == 0

    # During second CPU step (same token).
    env.run(until=0.006)
    assert cpu.level == 0
    assert server.ready_queue_len == 0

    env.run()
    assert cpu.level == 1
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0


def test_ram_gating_blocks_before_ready() -> None:
    """When RAM is scarce, blocks on RAM and must NOT inflate ready."""
    env = simpy.Environment()

    # Respect ServerResources(min RAM = 256).
    # Endpoint needs 256 MB → second request waits on RAM (not in ready).
    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 256},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: 0.005},
        ),
        Step(
            kind=EndpointStepIO.DB,
            step_operation={StepOperation.IO_WAITING_TIME: 0.020},
        ),
    )
    server, _ = _make_server_runtime(
        env,
        cpu_cores=2,
        ram_mb=256,
        steps=steps,
    )

    server.server_box.put(RequestState(id=50, initial_time=0.0))
    server.server_box.put(RequestState(id=51, initial_time=0.0))
    server.start()

    # Shortly after start: first runs; second is blocked on RAM, not in ready.
    env.run(until=0.002)
    assert server.ready_queue_len == 0

    env.run()
    assert server.ready_queue_len == 0
    assert server.io_queue_len == 0


def test_enabled_metrics_dict_populated() -> None:
    """ServerRuntime creates lists for every mandatory sampled metric."""
    env = simpy.Environment()
    server, _ = _make_server_runtime(env)

    mandatory = {
        SampledMetricName.RAM_IN_USE,
        SampledMetricName.READY_QUEUE_LEN,
        SampledMetricName.EVENT_LOOP_IO_SLEEP,
    }
    assert mandatory.issubset(server.enabled_metrics.keys())
