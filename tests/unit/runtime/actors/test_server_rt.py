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

import pytest
import simpy
from asyncfow.config.enums import (
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    EventMetricName,
    SampledMetricName,
    StepOperation,
)
from numpy.random import Generator as NpGenerator
from numpy.random import default_rng

from asyncflow.metrics.server import ServerClock
from asyncflow.resources.server_containers import build_containers
from asyncflow.runtime.actors import server as server_mod
from asyncflow.runtime.actors.server import ServerRuntime
from asyncflow.runtime.rqs_state import RequestState
from asyncflow.schemas.common.random_variables import RVConfig
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.endpoint import Endpoint, Step
from asyncflow.schemas.topology.nodes import NodesResources, Server

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
    res_spec = NodesResources(cpu_cores=cpu_cores, ram_mb=ram_mb)
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

    # Respect NodesResources(min RAM = 256).
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


# --------------------------------------------------------------------------- #
# CPU step: RVConfig is sampled via general_sampler                           #
# --------------------------------------------------------------------------- #

def test_cpu_step_uses_rvconfig_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    """CPU step duration follows the (patched) sampler result."""
    # Patch sampler: return 7 ms when mean=0.123 (CPU sentinel)
    def fake_sampler(cfg: RVConfig, rng: NpGenerator) -> float:
        return 0.007 if cfg.mean == 0.123 else 0.0

    monkeypatch.setattr(server_mod, "general_sampler", fake_sampler)

    env = simpy.Environment()
    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: RVConfig(mean=0.123)},
        ),
        Step(
            kind=EndpointStepIO.WAIT,
            step_operation={StepOperation.IO_WAITING_TIME: 0.010},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps, cpu_cores=1)
    cpu = server.server_resources["CPU"]

    server.server_box.put(RequestState(id=100, initial_time=0.0))
    server.start()

    # During CPU (7 ms)
    env.run(until=0.004)
    assert cpu.level == 0  # 1 core, held
    # After CPU finished
    env.run(until=0.008)
    assert cpu.level == 1  # released


# --------------------------------------------------------------------------- #
# IO step: RVConfig is sampled via general_sampler                            #
# --------------------------------------------------------------------------- #

def test_io_step_uses_rvconfig_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    """IO step duration follows the (patched) sampler result."""
    # Patch sampler: return 15 ms when mean=0.456 (IO sentinel)
    def fake_sampler(cfg: RVConfig, rng: NpGenerator) -> float:
        return 0.015 if cfg.mean == 0.456 else 0.0

    monkeypatch.setattr(server_mod, "general_sampler", fake_sampler)

    env = simpy.Environment()
    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: 0.002},
        ),
        Step(
            kind=EndpointStepIO.DB,
            step_operation={StepOperation.IO_WAITING_TIME: RVConfig(mean=0.456)},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps, cpu_cores=1)

    server.server_box.put(RequestState(id=200, initial_time=0.0))
    server.start()

    # After CPU (2 ms), inside IO (15 ms total)
    env.run(until=0.010)
    assert server.io_queue_len == 1
    # After IO finished
    env.run(until=0.020)
    assert server.io_queue_len == 0


# --------------------------------------------------------------------------- #
# Helpers: _compute_latency_cpu/_io dispatch to sampler and accept ints/floats #
# --------------------------------------------------------------------------- #

def test_helpers_sample_and_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helpers use sampler for RVConfig and accept int/float deterministics."""
    # Patch sampler to a fixed value
    def fake_sampler(cfg: RVConfig, rng: NpGenerator) -> float:
        return 0.123

    monkeypatch.setattr(server_mod, "general_sampler", fake_sampler)

    # Minimal runtime just to call methods
    env = simpy.Environment()

    # Call unbound methods with a real ServerRuntime instance to be safe
    # (we can build one via the existing factory)
    server, _ = _make_server_runtime(env)

    # RVConfig paths
    assert server._compute_latency_cpu(RVConfig(mean=1.0)) == pytest.approx(0.123) # noqa: SLF001
    assert server._compute_latency_io(RVConfig(mean=1.0)) == pytest.approx(0.123) # noqa: SLF001

    # Deterministic int/float paths
    assert server._compute_latency_cpu(2) == pytest.approx(2.0) # noqa: SLF001
    assert server._compute_latency_io(0.5) == pytest.approx(0.5) # noqa: SLF001


def test_server_clock_and_cumulative_metrics_default_pipeline() -> None:
    """
    Single request on default pipeline:
    - SERVICE_TIME should equal CPU(5ms)
    - IO_TIME should equal I/O(20ms)
    - WAITING_TIME should be ~0 (2 cores, no contention)
    - RQS_SERVER_CLOCK has start/finish with finish > start
    """
    env = simpy.Environment()
    server, _ = _make_server_runtime(env)  # default: 2 cores, default steps

    req_id = 301
    server.server_box.put(RequestState(id=req_id, initial_time=0.0))
    server.start()
    env.run()

    bucket = server.server_rqs_clock[req_id]
    # Clock present and well-formed
    assert EventMetricName.RQS_SERVER_CLOCK in bucket
    clock = bucket[EventMetricName.RQS_SERVER_CLOCK]
    assert isinstance(clock, ServerClock)
    assert clock.finish is not None
    assert clock.finish >= clock.start

    # Accumulators
    assert bucket[EventMetricName.SERVICE_TIME] == pytest.approx(0.005, abs=1e-9)
    assert bucket[EventMetricName.IO_TIME] == pytest.approx(0.020, abs=1e-9)
    assert bucket[EventMetricName.WAITING_TIME] == pytest.approx(0.0, abs=1e-12)

    # Server-side elapsed time should be at least the sum (avoid approx on RHS of >=)
    elapsed = clock.finish - clock.start
    assert elapsed >= (0.005 + 0.020) - 1e-9

def test_waiting_time_accumulates_under_contention() -> None:
    """
    With 1 core and two overlapping requests on a CPU-only endpoint:
    - The second request's WAITING_TIME ~= (first CPU time - overlap).
    """
    env = simpy.Environment()

    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: 0.008},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps, cpu_cores=1)

    first_id, second_id = 401, 402

    # First arrives at t=0.0
    server.server_box.put(RequestState(id=first_id, initial_time=0.0))

    # Schedule the second to actually arrive at t=0.001 (creates 1ms overlap)
    def _arrive_later() -> Generator[simpy.Event, None, None]:
        yield env.timeout(0.001)
        yield server.server_box.put(RequestState(id=second_id, initial_time=0.001))

    env.process(_arrive_later())

    server.start()
    env.run()

    b1 = server.server_rqs_clock[first_id]
    b2 = server.server_rqs_clock[second_id]

    # First: no waiting, service time = 8ms, no IO
    assert b1[EventMetricName.WAITING_TIME] == pytest.approx(0.0, abs=1e-9)
    assert b1[EventMetricName.SERVICE_TIME] == pytest.approx(0.008, abs=1e-9)
    assert b1[EventMetricName.IO_TIME] == pytest.approx(0.0, abs=1e-12)

    # Second: expected wait ≈ 0.007 (first CPU 8ms - 1ms overlap)
    assert b2[EventMetricName.WAITING_TIME] == pytest.approx(0.007, abs=2e-4)
    assert b2[EventMetricName.SERVICE_TIME] == pytest.approx(0.008, abs=1e-9)
    assert b2[EventMetricName.IO_TIME] == pytest.approx(0.0, abs=1e-12)


def test_metrics_follow_rv_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    With RVConfig on CPU and IO, SERVICE_TIME and IO_TIME must match
    the (patched) sampler outcomes.
    """
    # 6ms for CPU sentinel, 13ms for IO sentinel
    def fake_sampler(cfg: RVConfig, rng: NpGenerator) -> float:
        if cfg.mean == 0.321:
            return 0.006
        if cfg.mean == 0.654:
            return 0.013
        return 0.0

    monkeypatch.setattr(server_mod, "general_sampler", fake_sampler)

    env = simpy.Environment()
    steps = (
        Step(
            kind=EndpointStepRAM.RAM,
            step_operation={StepOperation.NECESSARY_RAM: 64},
        ),
        Step(
            kind=EndpointStepCPU.CPU_BOUND_OPERATION,
            step_operation={StepOperation.CPU_TIME: RVConfig(mean=0.321)},
        ),
        Step(
            kind=EndpointStepIO.DB,
            step_operation={StepOperation.IO_WAITING_TIME: RVConfig(mean=0.654)},
        ),
    )
    server, _ = _make_server_runtime(env, steps=steps, cpu_cores=1)

    req_id = 501
    server.server_box.put(RequestState(id=req_id, initial_time=0.0))
    server.start()
    env.run()

    bucket = server.server_rqs_clock[req_id]
    assert bucket[EventMetricName.SERVICE_TIME] == pytest.approx(0.006, abs=1e-9)
    assert bucket[EventMetricName.IO_TIME] == pytest.approx(0.013, abs=1e-9)
    assert bucket[EventMetricName.WAITING_TIME] == pytest.approx(0.0, abs=1e-12)

    clock = bucket[EventMetricName.RQS_SERVER_CLOCK]
    assert isinstance(clock, ServerClock)
    assert clock.finish is not None

    # Elapsed server-side time must be at least the sum of CPU+IO
    elapsed = clock.finish - clock.start
    assert elapsed >= (0.006 + 0.013) - 1e-9
