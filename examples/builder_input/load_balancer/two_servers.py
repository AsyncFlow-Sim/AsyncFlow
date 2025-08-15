#!/usr/bin/env python3
"""
Didactic example: build and run an AsyncFlow scenario **with a Load Balancer**
and two backend servers, using the builder (AsyncFlow) — no YAML.

Topology:
    generator ──> client ──> LB ──> srv-1
                               └─> srv-2
    srv-1 ──> client
    srv-2 ──> client

Load:
    ~120 active users, 20 req/min each (Poisson by default).

Servers:
    srv-1: 1 CPU core, 1GB RAM, endpoint with CPU→RAM→IO
    srv-2: 2 CPU cores, 2GB RAM, endpoint with RAM→IO(DB-like)

Network:
    2–3ms mean (exponential) latency on each edge.

What this script does:
  1) Build Pydantic models (generator, client, LB, servers, edges, settings).
  2) Compose the SimulationPayload via AsyncFlow (builder pattern).
  3) Run the simulation with SimulationRunner.
  4) Print latency stats, throughput timeline, and a sampled-metrics preview.
  5) Save a 2×2 plot figure (latency, throughput, server queues, RAM).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Mapping, TYPE_CHECKING

import numpy as np
import simpy

# ── AsyncFlow domain imports (match your working paths) ────────────────────────
from asyncflow.builder.asyncflow_builder import AsyncFlow
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.schemas.payload import SimulationPayload
from asyncflow.schemas.workload.rqs_generator import RqsGenerator
from asyncflow.schemas.settings.simulation import SimulationSettings
from asyncflow.schemas.topology.endpoint import Endpoint
from asyncflow.schemas.topology.nodes import Client, Server, LoadBalancer
from asyncflow.schemas.topology.edges import Edge
from asyncflow.config.constants import LatencyKey, SampledMetricName




# ─────────────────────────────────────────────────────────────
# Pretty printers (compact, readable output)
# ─────────────────────────────────────────────────────────────
def print_latency_stats(res: ResultsAnalyzer) -> None:
    stats: Mapping[LatencyKey, float] = res.get_latency_stats()
    print("\n════════ LATENCY STATS ════════")
    if not stats:
        print("(empty)")
        return

    order: List[LatencyKey] = [
        LatencyKey.TOTAL_REQUESTS,
        LatencyKey.MEAN,
        LatencyKey.MEDIAN,
        LatencyKey.STD_DEV,
        LatencyKey.P95,
        LatencyKey.P99,
        LatencyKey.MIN,
        LatencyKey.MAX,
    ]
    for key in order:
        if key in stats:
            print(f"{key.name:<20} = {stats[key]:.6f}")


def print_throughput(res: ResultsAnalyzer) -> None:
    timestamps, rps = res.get_throughput_series()
    print("\n════════ THROUGHPUT (req/sec) ════════")
    if not timestamps:
        print("(empty)")
        return
    for t, rate in zip(timestamps, rps):
        print(f"t={t:4.1f}s → {rate:6.2f} rps")


def print_sampled_preview(res: ResultsAnalyzer) -> None:
    sampled = res.get_sampled_metrics()
    print("\n════════ SAMPLED METRICS (preview) ════════")
    if not sampled:
        print("(empty)")
        return

    # Keys may be enums or strings depending on your analyzer; handle both.
    def _name(m):  # pragma: no cover
        return m.name if hasattr(m, "name") else str(m)

    for metric, series in sampled.items():
        print(f"\n📈 {_name(metric)}:")
        for entity, vals in series.items():
            head = list(vals[:5]) if vals else []
            print(f"  - {entity}: len={len(vals)}, first={head}")


# ─────────────────────────────────────────────────────────────
# Tiny helpers for sanity checks (optional)
# ─────────────────────────────────────────────────────────────
def _mean(series: Iterable[float]) -> float:
    arr = np.asarray(list(series), dtype=float)
    return float(np.mean(arr)) if arr.size else 0.0


def run_sanity_checks(
    runner: SimulationRunner,
    res: ResultsAnalyzer,
) -> None:
    print("\n════════ SANITY CHECKS (rough) ════════")
    w = runner.simulation_input.rqs_input
    lam_rps = (
        float(w.avg_active_users.mean)
        * float(w.avg_request_per_minute_per_user.mean)
        / 60.0
    )

    # Observed throughput
    _, rps_series = res.get_throughput_series()
    rps_observed = _mean(rps_series)
    print(
        f"• Mean throughput (rps)  expected≈{lam_rps:.3f}  "
        f"observed={rps_observed:.3f}"
    )

    sampled = res.get_sampled_metrics()
    ram_series = sampled.get(SampledMetricName.RAM_IN_USE, {})
    ioq_series = sampled.get(SampledMetricName.EVENT_LOOP_IO_SLEEP, {})
    ready_series = sampled.get(SampledMetricName.READY_QUEUE_LEN, {})

    ram_mean = _mean([_mean(v) for v in ram_series.values()]) if ram_series else 0.0
    ioq_mean = _mean([_mean(v) for v in ioq_series.values()]) if ioq_series else 0.0
    ready_mean = _mean([_mean(v) for v in ready_series.values()]) if ready_series else 0.0

    print(f"• Mean RAM in use (MB)    observed={ram_mean:.3f}")
    print(f"• Mean I/O queue length   observed={ioq_mean:.3f}")
    print(f"• Mean ready queue length observed={ready_mean:.3f}")


# ─────────────────────────────────────────────────────────────
# Build the LB + 2 servers scenario via AsyncFlow (builder)
# ─────────────────────────────────────────────────────────────
def build_payload_with_lb() -> SimulationPayload:
    """
    Construct the SimulationPayload programmatically using the builder:
      - Generator (120 users, 20 rpm each)
      - Client
      - Load balancer (round_robin) covering two servers
      - Two servers with distinct endpoints
      - Edges for all hops (gen→client, client→lb, lb→srv1/2, srv1/2→client)
      - Simulation settings: 600s total, sample period 20ms
    """
    # 1) Request generator
    generator = RqsGenerator(
        id="rqs-1",
        avg_active_users={"mean": 120},  # Poisson default
        avg_request_per_minute_per_user={"mean": 20},  # MUST be Poisson
        user_sampling_window=60,
    )

    # 2) Client
    client = Client(id="client-1")

    # 3) Servers with distinct endpoints
    ep_srv1 = Endpoint(
        endpoint_name="/api",
        # include 'probability' if your Endpoint schema supports it
        probability=1.0,  # remove if your Endpoint doesn't have this field
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.002}},
            {"kind": "ram", "step_operation": {"necessary_ram": 64}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.012}},
        ],
    )
    srv1 = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 1024},
        endpoints=[ep_srv1],
    )

    ep_srv2 = Endpoint(
        endpoint_name="/api",
        probability=1.0,  # remove if not supported in your schema
        steps=[
            {"kind": "ram", "step_operation": {"necessary_ram": 96}},
            {"kind": "io_db", "step_operation": {"io_waiting_time": 0.020}},
        ],
    )
    srv2 = Server(
        id="srv-2",
        server_resources={"cpu_cores": 2, "ram_mb": 2048},
        endpoints=[ep_srv2],
    )

    # 4) Load balancer (round_robin)
    lb = LoadBalancer(
        id="lb-1",
        algorithms="round_robin",
        server_covered={"srv-1", "srv-2"},
    )

    # 5) Edges with exponential latency (2–3 ms)
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
            id="lb-srv1",
            source="lb-1",
            target="srv-1",
            latency={"mean": 0.002, "distribution": "exponential"},
        ),
        Edge(
            id="lb-srv2",
            source="lb-1",
            target="srv-2",
            latency={"mean": 0.002, "distribution": "exponential"},
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

    # 6) Simulation settings
    settings = SimulationSettings(
        total_simulation_time=600,
        sample_period_s=0.02,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    # 7) Assemble the payload via the builder
    flow = (
        AsyncFlow()
        .add_generator(generator)
        .add_client(client)
        .add_servers(srv1, srv2)
        .add_load_balancer(lb)
        .add_edges(*edges)
        .add_simulation_settings(settings)
    )

    return flow.build_payload()


# ─────────────────────────────────────────────────────────────
# Main entry-point
# ─────────────────────────────────────────────────────────────
def main() -> None:
    """
    Build → wire → run the simulation, then print diagnostics and save plots.
    """
    env = simpy.Environment()
    payload = build_payload_with_lb()

    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    # Human-friendly diagnostics
    print_latency_stats(results)
    print_throughput(results)
    print_sampled_preview(results)

    # Optional sanity checks (very rough)
    run_sanity_checks(runner, results)

    # Save plots (2×2 figure)
    try:
        from matplotlib import pyplot as plt  # noqa: PLC0415

        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        results.plot_latency_distribution(axes[0, 0])
        results.plot_throughput(axes[0, 1])
        results.plot_server_queues(axes[1, 0])
        results.plot_ram_usage(axes[1, 1])
        fig.tight_layout()

        out_path = Path(__file__).parent / "two_servers.png"
        fig.savefig(out_path)
        print(f"\n🖼️  Plots saved to: {out_path}")
    except Exception as exc:  # Matplotlib not installed or plotting failed
        print(f"\n[plotting skipped] {exc!r}")


if __name__ == "__main__":
    main()
