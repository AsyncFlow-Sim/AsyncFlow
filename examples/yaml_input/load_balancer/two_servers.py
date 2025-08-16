#!/usr/bin/env python3
"""
Run an AsyncFlow scenario with a Load Balancer (2 servers) from YAML and print diagnostics.

What it does:
- Loads the simulation payload from YAML via `SimulationRunner.from_yaml`.
- Runs the simulation.
- Prints latency stats, 1s-bucket throughput, and a preview of sampled metrics.
- Saves four plots (latency histogram, throughput, server queues, RAM).
- Performs sanity checks (expected vs observed) with simple LB-aware heuristics.

Usage:
  python src/app/example/run_lb_from_yaml.py \
      --yaml src/app/example/data/two_servers_lb.yml
"""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Dict, List, Mapping

import matplotlib.pyplot as plt
import numpy as np
import simpy

from asyncflow.config.constants import (  # only for basic step-kind/ops inspection
    LatencyKey,
)
from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.runtime.simulation_runner import SimulationRunner


# ─────────────────────────────────────────────────────────────
# Pretty printers (same style as your single-server script)
# ─────────────────────────────────────────────────────────────
def print_latency_stats(res: ResultsAnalyzer) -> None:
    """Print latency statistics returned by the analyzer."""
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
# Sanity checks (LB-aware, still rough)
# ─────────────────────────────────────────────────────────────

def run_sanity_checks(runner: SimulationRunner, res: ResultsAnalyzer) -> None:
    """
    Sanity checks LB-aware (round-robin): observed vs expected
    """
    from asyncflow.config.constants import (
        EndpointStepCPU, EndpointStepIO, EndpointStepRAM, StepOperation, LatencyKey
    )
    import numpy as np

    def _mean(arr):
        a = np.asarray(list(arr), dtype=float)
        return float(a.mean()) if a.size else 0.0

    # 1) λ
    w = runner.simulation_input.rqs_input
    lam = float(w.avg_active_users.mean) * float(w.avg_request_per_minute_per_user.mean) / 60.0

    topo = runner.simulation_input.topology_graph
    servers = {s.id: s for s in topo.nodes.servers}
    client_id = topo.nodes.client.id
    lb = topo.nodes.load_balancer
    lb_id = lb.id if lb else None
    gen_id = runner.simulation_input.rqs_input.id

    # 2) LB (round_robin -> 1/N)
    if lb and lb.server_covered:
        covered = [sid for sid in lb.server_covered if sid in servers]
        N = max(1, len(covered))
        shares = {sid: 1.0 / N for sid in covered}
    else:
        only = next(iter(servers.keys()))
        shares = {only: 1.0}

    # 3) endpoint totals per server 
    def endpoint_totals(server):
        cpu_s = io_s = ram_mb = 0.0
        for ep in getattr(server, "endpoints", []) or []:
            prob = getattr(ep, "probability", 1.0)
            for step in ep.steps:
                k = step.kind
                op = step.step_operation
                if isinstance(k, EndpointStepCPU):
                    cpu_s += prob * float(op[StepOperation.CPU_TIME])
                elif isinstance(k, EndpointStepIO):
                    io_s += prob * float(op[StepOperation.IO_WAITING_TIME])
                elif isinstance(k, EndpointStepRAM):
                    ram_mb += prob * float(op[StepOperation.NECESSARY_RAM])
        return cpu_s, io_s, ram_mb

    per_srv = {sid: endpoint_totals(srv) for sid, srv in servers.items()}

    # 4) mappa latencies of edges per role (source,target) 
    mean_gen_client = 0.0; id_gen_client = None
    mean_client_lb  = 0.0; id_client_lb  = None
    mean_lb_srv     = {}   # sid -> mean
    mean_srv_client = {}   # sid -> mean
    id_lb_srv       = {}   # sid -> edge_id
    id_srv_client   = {}   # sid -> edge_id

    for e in topo.edges:
        s, t, mu = e.source, e.target, float(e.latency.mean)
        if s == gen_id and t == client_id:
            mean_gen_client = mu; id_gen_client = e.id
        elif s == client_id and lb_id and t == lb_id:
            mean_client_lb = mu; id_client_lb = e.id
        elif lb_id and s == lb_id and t in servers:
            mean_lb_srv[t] = mu; id_lb_srv[t] = e.id
        elif s in servers and t == client_id:
            mean_srv_client[s] = mu; id_srv_client[s] = e.id

    # 5) expected: average latencies 
    cpu_exp = sum(shares[sid] * per_srv[sid][0] for sid in shares)
    io_exp  = sum(shares[sid] * per_srv[sid][1] for sid in shares)
    net_exp = (
        mean_gen_client + mean_client_lb +
        sum(shares[sid] * (mean_lb_srv.get(sid, 0.0) + mean_srv_client.get(sid, 0.0)) for sid in shares)
    )
    latency_expected = cpu_exp + io_exp + net_exp

    # 6) observed: throughput & latencies
    stats = res.get_latency_stats()
    latency_observed = float(stats.get(LatencyKey.MEAN, 0.0))
    _, rps_series = res.get_throughput_series()
    rps_observed = _mean(rps_series)

    # 7) expected: RAM e I/O queue as a sum over server
    ram_expected = sum((shares[sid] * lam) * (per_srv[sid][0] + per_srv[sid][1]) * per_srv[sid][2] for sid in shares)
    ioq_expected = sum((shares[sid] * lam) * per_srv[sid][1] for sid in shares)

    # 8) observed: RAM (sum) and I/O queue sum
    sampled = res.get_sampled_metrics()
    ram_series = sampled.get("ram_in_use", {})
    ioq_series = sampled.get("event_loop_io_sleep", {})
    ram_observed = sum(_mean(vals) for vals in ram_series.values()) if ram_series else 0.0
    ioq_observed = sum(_mean(vals) for vals in ioq_series.values()) if ioq_series else 0.0

    # 9) print
    REL_TOL = 0.30
    def tick(label, exp, obs):
        delta = (abs(obs - exp) / abs(exp)) if exp else 0.0
        icon = "✓" if delta <= REL_TOL else "⚠"
        print(f"{icon} {label:<28} expected≈{exp:.3f}  observed={obs:.3f}  Δ={delta*100:.1f}%")

    print("\n════════ SANITY CHECKS (LB-aware) ════════")
    tick("Mean throughput (rps)", lam, rps_observed)
    tick("Mean latency (s)",      latency_expected, latency_observed)
    tick("Mean RAM (MB)",         ram_expected, ram_observed)
    tick("Mean I/O queue",        ioq_expected, ioq_observed)

    # 10) Edge concurrency estimation
    edge_conc = sampled.get("edge_concurrent_connection", {})
    if edge_conc:
        print("\n— Edge concurrency (LB-aware) —")
        means_obs = {eid: _mean(vals) for eid, vals in edge_conc.items()}

        if id_gen_client:
            tick(f"edge {id_gen_client}", lam * mean_gen_client, means_obs.get(id_gen_client, 0.0))
        if id_client_lb:
            tick(f"edge {id_client_lb}",  lam * mean_client_lb,  means_obs.get(id_client_lb, 0.0))

        for sid, p in shares.items():
            lam_i = p * lam
            eid = id_lb_srv.get(sid)
            if eid:
                tick(f"edge {eid}", lam_i * mean_lb_srv.get(sid, 0.0), means_obs.get(eid, 0.0))
            eid = id_srv_client.get(sid)
            if eid:
                tick(f"edge {eid}", lam_i * mean_srv_client.get(sid, 0.0), means_obs.get(eid, 0.0))

    # Extra 
    print("\n— Diagnostics —")
    print("λ={:.3f} rps | E[cpu]={:.3f}s  E[io]={:.3f}s  E[net]≈{:.3f}s | E[RAM/req]={:.1f} MB"
          .format(lam, cpu_exp, io_exp, net_exp, sum(shares[sid]*per_srv[sid][2] for sid in shares)))



# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main() -> None:
    """Parse args, run simulation, print/plot, sanity-check (LB topology)."""
    parser = ArgumentParser(description="Run AsyncFlow LB scenario from YAML and print outputs + sanity checks.")
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "two_servers_lb.yml",
        help="Path to the simulation YAML file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "two_servers.png",
        help="Path to the output image (plots).",
    )
    args = parser.parse_args()

    yaml_path: Path = args.yaml
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML not found: {yaml_path}")

    env = simpy.Environment()
    runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
    results: ResultsAnalyzer = runner.run()

    print_latency_stats(results)
    print_throughput(results)
    print_sampled_preview(results)

    run_sanity_checks(runner, results)
    save_all_plots(results, args.out)


if __name__ == "__main__":
    main()
