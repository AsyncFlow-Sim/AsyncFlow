#!/usr/bin/env python3
"""
Walkthrough: run a Load-Balanced (2 servers) AsyncFlow scenario from YAML.

What this script does
---------------------
1) Loads the SimulationPayload from a YAML file (round-robin LB, 2 identical servers).
2) Runs the simulation via `SimulationRunner`.
3) Prints a concise latency summary to stdout.
4) Saves plots **in the same folder as this script**:
   • `lb_dashboard.png` (Latency histogram + Throughput)
   • One figure per server with 3 panels: Ready Queue, I/O Queue, RAM usage.

How to use
----------
- Put this script and `two_servers_lb.yml` in the same directory.
- Run: `python run_lb_from_yaml.py`
"""

from __future__ import annotations

from pathlib import Path
import simpy
import matplotlib.pyplot as plt

from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer


def main() -> None:
    # Paths (same directory as this script)
    script_dir = Path(__file__).parent
    out_dir = script_dir / "two_servers_plot"
    out_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = script_dir.parent / "data" / "two_servers_lb.yml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML configuration not found: {yaml_path}")

    # Run the simulation
    print(f"🚀 Loading and running simulation from: {yaml_path}")
    env = simpy.Environment()
    runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
    results: ResultsAnalyzer = runner.run()
    print("✅ Simulation finished!")

    # Print concise latency summary
    print(results.format_latency_stats())

    # ---- Plots: dashboard (latency + throughput) ----
    fig_dash, axes_dash = plt.subplots(1, 2, figsize=(14, 5), dpi=160)
    results.plot_latency_distribution(axes_dash[0])
    results.plot_throughput(axes_dash[1])
    fig_dash.tight_layout()
    out_dashboard = out_dir / "lb_dashboard.png"
    fig_dash.savefig(out_dashboard, bbox_inches="tight")
    print(f"🖼️  Dashboard saved to: {out_dashboard}")

    # ---- Per-server metrics: one figure per server (Ready | I/O | RAM) ----
    for sid in results.list_server_ids():
        fig_row, axes = plt.subplots(1, 3, figsize=(16, 3.8), dpi=160)
        results.plot_single_server_ready_queue(axes[0], sid)
        results.plot_single_server_io_queue(axes[1], sid)
        results.plot_single_server_ram(axes[2], sid)
        fig_row.suptitle(f"Server metrics — {sid}", y=1.04, fontsize=14)
        fig_row.tight_layout()
        out_path = out_dir / f"lb_server_{sid}_metrics.png"
        fig_row.savefig(out_path, bbox_inches="tight")
        print(f"🖼️  Server metrics for '{sid}' saved to: {out_path}")


if __name__ == "__main__":
    main()
