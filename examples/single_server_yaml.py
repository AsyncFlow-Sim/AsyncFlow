#!/usr/bin/env python3
"""
Run a AsyncFlow scenario from a YAML file and print diagnostics.

What it does:
- Loads the simulation payload from YAML via `SimulationRunner.from_yaml`.
- Runs the simulation.
- Prints latency stats, 1s-bucket throughput, and a preview of sampled metrics.
- Saves four plots (latency histogram, throughput, server queues, RAM).
- Performs sanity checks (expected vs observed) with simple queueing heuristics.

Usage:
  python src/app/example/run_from_yaml.py \
      --yaml src/app/example/data/single_server.yml
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple

import matplotlib.pyplot as plt  
import numpy as np  
import simpy  
from asyncflow.config.constants import (  
    EndpointStepCPU,
    EndpointStepIO,
    EndpointStepRAM,
    LatencyKey,
    StepOperation,
)
from asyncflow.metrics.analyzer import ResultsAnalyzer  
from asyncflow.runtime.simulation_runner import SimulationRunner  


# ─────────────────────────────────────────────────────────────
# Pretty printers
# ─────────────────────────────────────────────────────────────
def print_latency_stats(res: ResultsAnalyzer) -> None:
    """Print latency statistics returned by the analyzer."""
    stats: Mapping[LatencyKey, float] = res.get_latency_stats()
    print("\n════════ LATENCY STATS ════════")
    if not stats:
        print("(empty)")
        return

    # Keep deterministic ordering for readability.
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
    """Print 1-second throughput buckets."""
    timestamps, rps = res.get_throughput_series()
    print("\n════════ THROUGHPUT (req/sec) ════════")
    if not timestamps:
        print("(empty)")
        return

    for t, rate in zip(timestamps, rps):
        print(f"t={t:4.1f}s → {rate:6.2f} rps")


def print_sampled_preview(res: ResultsAnalyzer) -> None:
    """Print first 5 samples of each sampled metric series."""
    sampled: Dict[str, Dict[str, List[float]]] = res.get_sampled_metrics()
    print("\n════════ SAMPLED METRICS ════════")
    if not sampled:
        print("(empty)")
        return

    for metric, series in sampled.items():
        print(f"\n📈 {metric}:")
        for entity, vals in series.items():
            head = list(vals[:5]) if vals else []
            print(f"  - {entity}: len={len(vals)}, first={head}")


# ─────────────────────────────────────────────────────────────
# Plotting
# ─────────────────────────────────────────────────────────────
def save_all_plots(res: ResultsAnalyzer, out_path: Path) -> None:
    """Generate the 2x2 plot figure and save it to `out_path`."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    res.plot_latency_distribution(axes[0, 0])
    res.plot_throughput(axes[0, 1])
    res.plot_server_queues(axes[1, 0])
    res.plot_ram_usage(axes[1, 1])
    fig.tight_layout()
    fig.savefig(out_path)
    print(f"\n🖼️  Plots saved to: {out_path}")


# ─────────────────────────────────────────────────────────────
# Sanity checks (expected vs observed)
# ─────────────────────────────────────────────────────────────
REL_TOL = 0.30  # 30% tolerance for rough sanity checks


def _tick(label: str, expected: float, observed: float) -> None:
    """Print a ✓ or ⚠ depending on relative error vs `REL_TOL`."""
    if expected == 0.0:
        delta_pct = 0.0
        icon = "•"
    else:
        delta = abs(observed - expected) / abs(expected)
        delta_pct = delta * 100.0
        icon = "✓" if delta <= REL_TOL else "⚠"
    print(f"{icon} {label:<28} expected≈{expected:.3f}  observed={observed:.3f}  Δ={delta_pct:.1f}%")


def _endpoint_totals(runner: SimulationRunner) -> Tuple[float, float, float]:
    """
    Return (CPU_seconds, IO_seconds, RAM_MB) of the first endpoint on the first server.

    This keeps the check simple. If you use multiple endpoints weighted by probability,
    extend this function to compute a probability-weighted average.
    """
    servers = runner.simulation_input.topology_graph.nodes.servers
    if not servers or not servers[0].endpoints:
        return (0.0, 0.0, 0.0)

    ep = servers[0].endpoints[0]
    cpu_s = 0.0
    io_s = 0.0
    ram_mb = 0.0

    for step in ep.steps:
        if isinstance(step.kind, EndpointStepCPU):
            cpu_s += float(step.step_operation[StepOperation.CPU_TIME])
        elif isinstance(step.kind, EndpointStepIO):
            io_s += float(step.step_operation[StepOperation.IO_WAITING_TIME])
        elif isinstance(step.kind, EndpointStepRAM):
            ram_mb += float(step.step_operation[StepOperation.NECESSARY_RAM])

    return (cpu_s, io_s, ram_mb)


def _edges_mean_latency(runner: SimulationRunner) -> float:
    """Sum of edge mean latencies across the graph (simple additive approximation)."""
    return float(sum(e.latency.mean for e in runner.simulation_input.topology_graph.edges))


def _mean(series: Iterable[float]) -> float:
    """Numerically stable mean for a generic float iterable."""
    arr = np.asarray(list(series), dtype=float)
    return float(np.mean(arr)) if arr.size else 0.0


def run_sanity_checks(runner: SimulationRunner, res: ResultsAnalyzer) -> None:
    """
    Compare expected vs observed metrics using back-of-the-envelope approximations.

    Approximations used:
      - Throughput ≈ λ = users * RPM / 60
      - Mean latency ≈ CPU_s + IO_s + NET_s (ignores queueing inside the server)
      - Mean RAM ≈ λ * T_srv * RAM_per_request (Little’s law approximation)
      - Mean I/O queue length ≈ λ * IO_s
      - Edge concurrency ≈ λ * edge_mean_latency
    """
    print("\n════════ SANITY CHECKS (expected vs observed) ════════")

    # Arrival rate λ (requests per second)
    w = runner.simulation_input.rqs_input
    lam_rps = float(w.avg_active_users.mean) * float(w.avg_request_per_minute_per_user.mean) / 60.0

    # Endpoint sums
    cpu_s, io_s, ram_mb = _endpoint_totals(runner)
    net_s = _edges_mean_latency(runner)
    t_srv = cpu_s + io_s
    latency_expected = cpu_s + io_s + net_s

    # Observed latency, throughput
    stats = res.get_latency_stats()
    latency_observed = float(stats.get(LatencyKey.MEAN, 0.0))
    _, rps_series = res.get_throughput_series()
    rps_observed = _mean(rps_series)

    # Observed RAM and queues
    sampled = res.get_sampled_metrics()
    ram_series = sampled.get("ram_in_use", {})
    ram_means = [_mean(vals) for vals in ram_series.values()]
    ram_observed = float(sum(ram_means)) if ram_means else 0.0

    ready_series = sampled.get("ready_queue_len", {})
    ioq_series = sampled.get("event_loop_io_sleep", {})
    ready_observed = _mean([_mean(v) for v in ready_series.values()]) if ready_series else 0.0
    ioq_observed = _mean([_mean(v) for v in ioq_series.values()]) if ioq_series else 0.0

    # Expected quantities (very rough)
    rps_expected = lam_rps
    ram_expected = lam_rps * t_srv * ram_mb
    ioq_expected = lam_rps * io_s

    _tick("Mean throughput (rps)", rps_expected, rps_observed)
    _tick("Mean latency (s)", latency_expected, latency_observed)
    _tick("Mean RAM (MB)", ram_expected, ram_observed)
    _tick("Mean I/O queue", ioq_expected, ioq_observed)

    # Edge concurrency
    edge_conc = sampled.get("edge_concurrent_connection", {})
    if edge_conc:
        print("\n— Edge concurrency —")
        edge_means: Dict[str, float] = {eid: _mean(vals) for eid, vals in edge_conc.items()}
        for e in runner.simulation_input.topology_graph.edges:
            exp = lam_rps * float(e.latency.mean)
            obs = edge_means.get(e.id, 0.0)
            _tick(f"edge {e.id}", exp, obs)

    # Extra diagnostics
    print("\n— Diagnostics —")
    print(
        "λ={:.3f} rps | CPU_s={:.3f}  IO_s={:.3f}  NET_s≈{:.3f} | RAM/req={:.1f} MB"
        .format(lam_rps, cpu_s, io_s, net_s, ram_mb)
    )
    print("T_srv={:.3f}s  →  RAM_expected≈λ*T_srv*RAM = {:.1f} MB".format(t_srv, ram_expected))


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main() -> None:
    """Entry-point: parse args, run simulation, print/plot, sanity-check."""
    parser = ArgumentParser(description="Run AsyncFlow from YAML and print outputs + sanity checks.")
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path(__file__).parent / "data" /"single_server.yml",
        help="Path to the simulation YAML file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "single_server_yml.png",
        help="Path to the output image (plots).",
    )
    args = parser.parse_args()

    yaml_path: Path = args.yaml
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML not found: {yaml_path}")

    # Build runner from YAML and execute
    env = simpy.Environment()
    runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
    results: ResultsAnalyzer = runner.run()

    # Prints
    print_latency_stats(results)
    print_throughput(results)
    print_sampled_preview(results)

    # Sanity checks
    run_sanity_checks(runner, results)

    # Plots
    save_all_plots(results, args.out)


if __name__ == "__main__":
    main()
