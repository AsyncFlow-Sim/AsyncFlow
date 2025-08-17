"""
AsyncFlow — YAML single-server example: run and export charts.

System (single server)
  generator → client → server → client

Load
  ~100 active users, ~20 requests/min each (stochastic aggregate).

Server
  1 CPU core, 2 GB RAM, endpoint "ep-1":
    CPU(1 ms) → RAM(100 MB) → I/O wait (100 ms)
  Semantics:
    - CPU step blocks the event loop
    - RAM step holds a working set until the request leaves the server
    - I/O step is non-blocking (event-loop friendly)

Network
  Each edge has exponential latency with mean 3 ms.

Simulation settings
  Duration: 500 s
  Sampling period: 50 ms

What this script does
  1) Loads the YAML scenario and runs the simulation.
  2) Prints latency statistics to stdout.
  3) Saves charts next to this script:
     - Dashboard PNG: latency histogram (mean/P50/P95/P99)
       and throughput (mean/P95/max) side-by-side.
     - Per-server PNGs: Ready queue, I/O queue, and RAM usage for each server.
"""


from __future__ import annotations

import logging
from pathlib import Path

# SimPy environment is required by SimulationRunner.from_yaml
import simpy

# matplotlib is needed to create figures for plotting
import matplotlib.pyplot as plt

# The only imports a user needs to run a simulation
from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.runtime.simulation_runner import SimulationRunner

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    """Defines paths, runs the simulation, and generates all outputs."""
    # --- 1. Define File Paths ---
    script_dir = Path(__file__).parent           # <-- same folder as this file
    out_dir = script_dir                         # <-- save outputs here
    yaml_path = script_dir.parent / "data" / "single_server.yml"
    output_base_name = "single_server_results"   # prefix for all output files

    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML configuration file not found: {yaml_path}")

    # --- 2. Run the Simulation ---
    print(f"🚀 Loading and running simulation from: {yaml_path}")
    env = simpy.Environment()  # Create the SimPy environment
    runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)  # pass env
    results: ResultsAnalyzer = runner.run()
    print("✅ Simulation finished!")

    # Plot 1: The main dashboard (Latency Distribution + Throughput)
    fig_base, axes_base = plt.subplots(1, 2, figsize=(14, 5))
    results.plot_base_dashboard(axes_base[0], axes_base[1])
    fig_base.tight_layout()
    base_plot_path = out_dir / f"{output_base_name}_dashboard.png"
    fig_base.savefig(base_plot_path)
    print(f"🖼️  Base dashboard saved to: {base_plot_path}")

    # Plot 2: Individual plots for each server's metrics
    server_ids = results.list_server_ids()
    for sid in server_ids:
        # Ready queue (separate)
        fig_rdy, ax_rdy = plt.subplots(figsize=(10, 5))
        results.plot_single_server_ready_queue(ax_rdy, sid)
        fig_rdy.tight_layout()
        rdy_path = out_dir / f"{output_base_name}_ready_queue_{sid}.png"
        fig_rdy.savefig(rdy_path)
        print(f"🖼️  Ready queue for '{sid}' saved to: {rdy_path}")

        # I/O queue (separate)
        fig_io, ax_io = plt.subplots(figsize=(10, 5))
        results.plot_single_server_io_queue(ax_io, sid)
        fig_io.tight_layout()
        io_path = out_dir / f"{output_base_name}_io_queue_{sid}.png"
        fig_io.savefig(io_path)
        print(f"🖼️  I/O queue for '{sid}' saved to: {io_path}")

        # RAM (separate)
        fig_r, ax_r = plt.subplots(figsize=(10, 5))
        results.plot_single_server_ram(ax_r, sid)
        fig_r.tight_layout()
        r_path = out_dir / f"{output_base_name}_ram_{sid}.png"
        fig_r.savefig(r_path)
        print(f"🖼️  RAM plot for '{sid}' saved to: {r_path}")


if __name__ == "__main__":
    main()
