#!/usr/bin/env python3
"""
Didactic example: build and run a AsyncFlow scenario **without** YAML,
using the 'pybuilder' (AsyncFlow) to assemble the SimulationPayload.

Scenario reproduced (same as the previous YAML):
    generator ──edge──> client ──edge──> server ──edge──> client

Load:
    ~100 active users, 20 req/min each.

Server:
    1 CPU core, 2GB RAM, endpoint with steps:
        CPU(1ms) → RAM(100MB) → IO(100ms)

Network:
    3ms mean (exponential) latency on each edge.

What this script does:
  1) Build Pydantic models (generator, client, server, edges, settings).
  2) Compose the final SimulationPayload via AsyncFlow (builder pattern).
  3) Run the simulation with SimulationRunner.
  4) Print latency stats, throughput timeline, and a sampled-metrics preview.
  5) (Optional) Visualize the topology with Matplotlib.

Run:
    python run_with_pybuilder.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Mapping

import numpy as np
import simpy

# ── AsyncFlow domain imports ───────────────────────────────────────────────────
from asyncflow.pybuilder.input_builder import AsyncFlow
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.schemas.full_simulation_input import SimulationPayload
from asyncflow.schemas.rqs_generator_input import RqsGeneratorInput
from asyncflow.schemas.simulation_settings_input import SimulationSettings
from asyncflow.schemas.system_topology.endpoint import Endpoint
from asyncflow.schemas.system_topology.full_system_topology import (
    Client,
    Edge,
    Server,
)

from asyncflow.config.constants import LatencyKey, SampledMetricName


# ─────────────────────────────────────────────────────────────
# Pretty printers (compact, readable output)
# ─────────────────────────────────────────────────────────────
def print_latency_stats(res: ResultsAnalyzer) -> None:
    """Print latency statistics calculated by the analyzer."""
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
    """Print the 1-second throughput buckets."""
    timestamps, rps = res.get_throughput_series()
    print("\n════════ THROUGHPUT (req/sec) ════════")
    if not timestamps:
        print("(empty)")
        return

    for t, rate in zip(timestamps, rps):
        print(f"t={t:4.1f}s → {rate:6.2f} rps")


def print_sampled_preview(res: ResultsAnalyzer) -> None:
    """
    Print a small preview for each sampled metric series (first 5 values).
    This helps verify that sampler pipelines are running.
    """
    sampled = res.get_sampled_metrics()
    print("\n════════ SAMPLED METRICS (preview) ════════")
    if not sampled:
        print("(empty)")
        return

    for metric, series in sampled.items():
        metric_name = (
            metric.name if isinstance(metric, SampledMetricName) else str(metric)
        )
        print(f"\n📈 {metric_name}:")
        for entity, vals in series.items():
            head = list(vals[:5]) if vals else []
            print(f"  - {entity}: len={len(vals)}, first={head}")


# ─────────────────────────────────────────────────────────────
# Tiny helpers for sanity checks (optional)
# ─────────────────────────────────────────────────────────────
def _mean(series: Iterable[float]) -> float:
    """Numerically stable mean for a generic float iterable."""
    arr = np.asarray(list(series), dtype=float)
    return float(np.mean(arr)) if arr.size else 0.0


def run_sanity_checks(
    runner: SimulationRunner,
    res: ResultsAnalyzer,
) -> None:
    """
    Back-of-the-envelope checks to compare rough expectations vs observations.
    These are intentionally simplistic approximations.
    """
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
    print(f"• Mean throughput (rps)  expected≈{lam_rps:.3f}  "
          f"observed={rps_observed:.3f}")

    # A few sampled signals (RAM, queues) just to show they are populated.
    sampled = res.get_sampled_metrics()
    ram_series = sampled.get(SampledMetricName.RAM_IN_USE, {})
    ioq_series = sampled.get(SampledMetricName.EVENT_LOOP_IO_SLEEP, {})
    ready_series = sampled.get(SampledMetricName.READY_QUEUE_LEN, {})

    ram_mean = _mean([_mean(v) for v in ram_series.values()]) if ram_series else 0.0
    ioq_mean = _mean([_mean(v) for v in ioq_series.values()]) if ioq_series else 0.0
    ready_mean = (
        _mean([_mean(v) for v in ready_series.values()]) if ready_series else 0.0
    )

    print(f"• Mean RAM in use (MB)    observed={ram_mean:.3f}")
    print(f"• Mean I/O queue length   observed={ioq_mean:.3f}")
    print(f"• Mean ready queue length observed={ready_mean:.3f}")


# ─────────────────────────────────────────────────────────────
# Build the same scenario via AsyncFlow (pybuilder)
# ─────────────────────────────────────────────────────────────
def build_payload_with_pybuilder() -> SimulationPayload:
    """
    Construct the SimulationPayload programmatically using the builder.

    This mirrors the YAML:
      - Generator (100 users, 20 rpm each)
      - Client
      - One server with a single endpoint (CPU → RAM → IO)
      - Three edges with exponential latency (3ms mean)
      - Simulation settings: 500s total, sample period 50ms
    """
    # 1) Request generator
    generator = RqsGeneratorInput(
        id="rqs-1",
        avg_active_users={"mean": 100},
        avg_request_per_minute_per_user={"mean": 20},
        user_sampling_window=60,
    )

    # 2) Client
    client = Client(id="client-1")

    # 3) Server (1 CPU core, 2GB RAM) with one endpoint and three steps
    #    We let Pydantic coerce nested dicts for the endpoint steps.
    endpoint = Endpoint(
        endpoint_name="ep-1",
        probability=1.0,
        steps=[
            {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.001}},
            {"kind": "ram", "step_operation": {"necessary_ram": 100}},
            {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.1}},
        ],
    )

    server = Server(
        id="srv-1",
        server_resources={"cpu_cores": 1, "ram_mb": 2048},
        endpoints=[endpoint],
    )

    # 4) Edges: exponential latency with 3ms mean (same as YAML)
    e_gen_client = Edge(
        id="gen-to-client",
        source="rqs-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_client_server = Edge(
        id="client-to-server",
        source="client-1",
        target="srv-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )
    e_server_client = Edge(
        id="server-to-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    )

    # 5) Simulation settings
    settings = SimulationSettings(
        total_simulation_time=500,
        sample_period_s=0.05,
        enabled_sample_metrics=[
            "ready_queue_len",
            "event_loop_io_sleep",
            "ram_in_use",
            "edge_concurrent_connection",
        ],
        enabled_event_metrics=["rqs_clock"],
    )

    # 6) Assemble the payload via the builder (AsyncFlow).
    #    The builder will validate the final structure on build.
    flow = (
        AsyncFlow()
        .add_generator(generator)
        .add_client(client)
        .add_servers(server)
        .add_edges(e_gen_client, e_client_server, e_server_client)
        .add_simulation_settings(settings)
    )

    return flow.build_payload()


# ─────────────────────────────────────────────────────────────
# Main entry-point
# ─────────────────────────────────────────────────────────────
def main() -> None:
    """
    Build → wire → run the simulation, then print diagnostics.
    Mirrors run_from_yaml.py but uses the pybuilder to construct the input.
    Also saves a 2x2 plot figure (latency, throughput, server queues, RAM).
    """
    env = simpy.Environment()
    payload = build_payload_with_pybuilder()

    runner = SimulationRunner(env=env, simulation_input=payload)
    results: ResultsAnalyzer = runner.run()

    # Human-friendly diagnostics
    print_latency_stats(results)
    print_throughput(results)
    print_sampled_preview(results)

    # Optional sanity checks (very rough)
    run_sanity_checks(runner, results)

    # Save plots (2x2 figure), same layout as in the YAML-based example
    try:
        from matplotlib import pyplot as plt  # noqa: PLC0415

        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        results.plot_latency_distribution(axes[0, 0])
        results.plot_throughput(axes[0, 1])
        results.plot_server_queues(axes[1, 0])
        results.plot_ram_usage(axes[1, 1])
        fig.tight_layout()

        out_path = Path(__file__).parent / "single_server_pybuilder.png"
        fig.savefig(out_path)
        print(f"\n🖼️  Plots saved to: {out_path}")
    except Exception as exc:  # Matplotlib not installed or plotting failed
        print(f"\n[plotting skipped] {exc!r}")
        
if __name__ == "__main__":
    main()