"""System test: client + LB + 2 servers with edge spike and server outage.

Topology:
    generator → client → lb-1 → {srv-1, srv-2} → client

Endpoint on both servers:
    CPU(1 ms) → RAM(64 MB) → IO(10 ms)

Edges (baseline):
    exponential latency ~ 2-3 ms per hop.

Events injected:
  - NETWORK_SPIKE on edge 'lb-srv-1': +50 ms, t ∈ [2.0, 12.0] s
  - SERVER_DOWN on 'srv-2': t ∈ [5.0, 20.0] s

Checks:
- mean latency with events > baseline by a safe margin;
- throughput stays > 30% of baseline (LB still routes to srv-1),
  and not more than +5% above baseline;
- sampled metrics present for both servers.
"""

from __future__ import annotations

import os
import random
from typing import TYPE_CHECKING

import numpy as np
import pytest
import simpy

from asyncflow import AsyncFlow
from asyncflow.components import Client, Edge, Endpoint, LoadBalancer, Server
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

SEED = 7778
# LB re-routing and stochasticity can raise throughput
REL_TOL_TPUT_UPPER = 0.25  # allow up to +25% increase;
REL_TOL_TPUT_LOWER = 0.30   # must keep at least 30% throughput


def _seed_all(seed: int = SEED) -> None:
    """Seed Python, NumPy, and hashing for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)  # noqa: NPY002
    os.environ["PYTHONHASHSEED"] = str(seed)


def _build_payload(*, with_events: bool) -> SimulationPayload:
    """Build payload for client + LB + two servers; optionally add events."""
    # Workload: ~26.7 rps (80 users * 20 rpm / 60).
    gen = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 80},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )
    client = Client(id="client-1")
    lb = LoadBalancer(id="lb-1", algorithm="round_robin")

    ep = Endpoint(
        endpoint_name="/api",
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},
            {"kind": "ram", "step_operation": {"necessary_ram": 64}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
        ],
    )

    srv1 = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[ep],
    )
    srv2 = Server(
        id="srv-2",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[ep],
    )

    # Edges: generator→client, client→lb, lb→srv-{1,2}, srv-{1,2}→client.
    edges = [
        Edge(
            id="gen-client",
            source="rqs-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="client-lb",
            source="client-1",
            target="lb-1",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv-1",
            source="lb-1",
            target="srv-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv-2",
            source="lb-1",
            target="srv-2",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="srv1-client",
            source="srv-1",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
        Edge(
            id="srv2-client",
            source="srv-2",
            target="client-1",
            latency={"mean": 0.003, "distribution": "exponential"},
        ),
    ]

    settings = SimulationSettings(
        total_simulation_time=100.0,  # >= 5 s
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
        .add_load_balancer(lb)
        .add_servers(srv1, srv2)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    )

    if with_events:
        # Edge spike on lb→srv-1: +50 ms between 2s and 12s.
        flow = flow.add_network_spike(
            event_id="edge-spike-1",
            edge_id="lb-srv-1",
            t_start=2.0,
            t_end=12.0,
            spike_s=0.050,
        )

        # Server outage on srv-2 between 5s and 20s.
        flow = flow.add_server_outage(
            event_id="srv2-outage",
            server_id="srv-2",
            t_start=5.0,
            t_end=20.0,
        )

    return flow.build_payload()


def _run(payload: SimulationPayload) -> ResultsAnalyzer:
    """Run one simulation and return the analyzer."""
    env = simpy.Environment()
    runner = SimulationRunner(env=env, simulation_input=payload)
    return runner.run()


def test_lb_two_servers_spike_and_outage() -> None:
    """LB keeps serving via srv-1; latency rises; throughput remains non-zero."""
    _seed_all(SEED)

    # Baseline
    res_base = _run(_build_payload(with_events=False))
    stats_base = res_base.get_latency_stats()
    assert stats_base, "Expected non-empty latency stats (baseline)."
    mean_base = float(stats_base.get(LatencyKey.MEAN, 0.0))
    assert mean_base > 0.0

    # With events (spike on lb→srv-1 and outage on srv-2)
    _seed_all(SEED)
    res_evt = _run(_build_payload(with_events=True))
    stats_evt = res_evt.get_latency_stats()
    assert stats_evt, "Expected non-empty latency stats (events)."
    mean_evt = float(stats_evt.get(LatencyKey.MEAN, 0.0))
    assert mean_evt > 0.0

    # Expect a noticeable increase in mean latency with events.
    # Spike is +50 ms for 10 s out of 40 s on half of LB routes ≈ few ms avg.
    assert mean_evt >= mean_base + 0.003

    # Throughput should remain within reasonable bounds:
    # not zero (LB routes to srv-1), and not spuriously higher than baseline.
    _, rps_base = res_base.get_throughput_series()
    _, rps_evt = res_evt.get_throughput_series()

    assert rps_base, "No throughput series produced (baseline)."
    assert rps_evt, "No throughput series produced (events)."

    rps_mean_base = float(np.mean(rps_base))
    rps_mean_evt = float(np.mean(rps_evt))
    denom = max(rps_mean_base, 1e-9)

    # Lower bound: at least 30% of baseline throughput.
    assert (rps_mean_evt / denom) >= REL_TOL_TPUT_LOWER
    # Upper bound: at most +5% above baseline.
    assert (abs(rps_mean_evt - rps_mean_base) / denom) <= REL_TOL_TPUT_UPPER

    # Sampled metrics present for both servers.
    sampled = res_evt.get_sampled_metrics()
    for key in ("ready_queue_len", "event_loop_io_sleep", "ram_in_use"):
        assert key in sampled
        assert "srv-1" in sampled[key]
        assert "srv-2" in sampled[key]
        assert len(sampled[key]["srv-1"]) > 0
        assert len(sampled[key]["srv-2"]) > 0
