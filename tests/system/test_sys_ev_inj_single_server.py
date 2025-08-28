"""System test: single server with a deterministic network spike on an edge.

Topology:
    generator → client → srv-1 → client

Endpoint:
    CPU(1 ms) → RAM(64 MB) → IO(10 ms)

Edges (baseline):
    exponential latency ~ 2-3 ms per hop.

Event injected:
    NETWORK_SPIKE on edge 'client-srv' adding +50 ms between t=[0.5, 2.5] s.

Checks:
- mean latency with spike > mean latency without spike by a safe margin;
- throughput stays roughly similar (the spike increases latency, not λ);
- sampled metrics present.

This test runs *two* short simulations (same seed):
  (A) baseline (no events)
  (B) with edge spike
Then compares their metrics.
"""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING

import numpy as np
import pytest
import simpy

from asyncflow import AsyncFlow
from asyncflow.components import Client, Edge, Endpoint, Server
from asyncflow.config.constants import LatencyKey
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.settings import SimulationSettings
from asyncflow.workload import RqsGenerator

if TYPE_CHECKING:
    from asyncflow.metrics.analyzer import ResultsAnalyzer
    from asyncflow.schemas.payload import SimulationPayload

pytestmark = [
    pytest.mark.system,
    pytest.mark.skipif(
        os.getenv("ASYNCFLOW_RUN_SYSTEM_TESTS") != "1",
        reason=(
            "System tests disabled "
            "(set ASYNCFLOW_RUN_SYSTEM_TESTS=1 to run)."
        ),
    ),
]

SEED = 4240
REL_TOL_TPUT = 0.20  # throughput should be within ±20%
                     

def _seed_all(seed: int = SEED) -> None:
    """Seed Python, NumPy, and hashing for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)  # noqa: NPY002
    os.environ["PYTHONHASHSEED"] = str(seed)


def _build_payload(*, with_spike: bool) -> SimulationPayload:
    """Build a single-server payload; optionally inject an edge spike."""
    # Workload: ~26.7 rps (80 users * 20 rpm / 60).
    gen = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 80},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )
    client = Client(id="client-1")

    ep = Endpoint(
        endpoint_name="/api",
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},
            {"kind": "ram", "step_operation": {"necessary_ram": 64}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
        ],
    )
    srv = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[ep],
    )

    # Edges: baseline exponential latencies around a few milliseconds.
    edges = [
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="client-srv",
            source="client-1",
            target="srv-1",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="srv-client",
            source="srv-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
    ]

    # Simulation horizon covers the whole spike window.
    settings = SimulationSettings(
        total_simulation_time=100.0,  # >= 5 (schema lower bound)
        sample_period_s=0.05,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    flow = (
        AsyncFlow()
        .add_generator(gen)
        .add_client(client)
        .add_servers(srv)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    )

    if with_spike:
        # Add +50 ms to client→server between t=[0.5, 2.5] seconds.
        flow = flow.add_network_spike(
            event_id="net-spike-1",
            edge_id="client-srv",
            t_start=0.5,
            t_end=2.5,
            spike_s=0.050,
        )

    return flow.build_payload()


def _run(payload: SimulationPayload) -> ResultsAnalyzer:
    """Run one simulation and return the analyzer."""
    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=payload)
    return runner.run()


def test_edge_latency_spike_increases_mean_latency() -> None:
    """The injected edge spike must measurably increase mean latency."""
    _seed_all(SEED)

    # Baseline.
    res_base = _run(_build_payload(with_spike=False))
    stats_base = res_base.get_latency_stats()
    assert stats_base, "Expected non-empty latency stats (baseline)."
    mean_base = float(stats_base.get(LatencyKey.MEAN, 0.0))
    assert mean_base > 0.0

    # With spike.
    _seed_all(SEED)  # identical workload chronology, only edge differs
    res_spike = _run(_build_payload(with_spike=True))
    stats_spike = res_spike.get_latency_stats()
    assert stats_spike, "Expected non-empty latency stats (spike)."
    mean_spike = float(stats_spike.get(LatencyKey.MEAN, 0.0))
    assert mean_spike > 0.0

    # The spike window covers part of the horizon and adds +50 ms on
    # the client→server hop; expect a noticeable average increase.
    assert mean_spike >= mean_base * 1.02

    # Throughput should remain roughly similar (spike adds latency, not λ).
    _, rps_base = res_base.get_throughput_series()
    _, rps_spike = res_spike.get_throughput_series()

    assert rps_base, "No throughput series produced (baseline)."
    assert rps_spike, "No throughput series produced (spike)."

    rps_mean_base = float(np.mean(rps_base))
    rps_mean_spike = float(np.mean(rps_spike))
    denom = max(rps_mean_base, 1e-9)
    rel_diff = abs(rps_mean_spike - rps_mean_base) / denom
    assert rel_diff <= REL_TOL_TPUT

    # Basic sampled metrics should be present.
    sampled = res_spike.get_sampled_metrics()
    for key in ("ready_queue_len", "event_loop_io_sleep", "ram_in_use"):
        assert key in sampled
        assert "srv-1" in sampled[key]
        assert len(sampled[key]["srv-1"]) > 0
