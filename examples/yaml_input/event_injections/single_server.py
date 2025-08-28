"""
Run the YAML scenario with event injections and export charts.

Scenario file:
  data/event_inj_single_server.yml

Outputs (saved under a folder next to this script):
  examples/yaml_input/event_injections/single_server_plot/
    - event_inj_single_server_dashboard.png
    - event_inj_single_server_ready_queue_<server>.png
    - event_inj_single_server_io_queue_<server>.png
    - event_inj_single_server_ram_<server>.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import simpy

from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.runtime.simulation_runner import SimulationRunner


def main() -> None:
    """Defines paths, runs the simulation, and generates all outputs."""
    # --- 1. Define File Paths ---
    script_dir = Path(__file__).parent           # same folder as this file
    yaml_path = script_dir.parent / "data" / "event_inj_single_server.yml"
    output_base_name = "event_inj_single_server"  # prefix for output files

    if not yaml_path.exists():
        msg = f"YAML configuration file not found: {yaml_path}"
        raise FileNotFoundError(msg)

    # Create/ensure the output directory:
    out_dir = script_dir / "single_server_plot"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 2. Run the Simulation ---
    env = simpy.Environment()
    runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
    results: ResultsAnalyzer = runner.run()

    # --- 3. Dashboard (latency + throughput) ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    results.plot_base_dashboard(axes[0], axes[1])
    fig.tight_layout()
    dash_path = out_dir / f"{output_base_name}_dashboard.png"
    fig.savefig(dash_path)
    print(f"Saved: {dash_path}")

    # --- 4. Per-server plots ---
    for sid in results.list_server_ids():
        # Ready queue
        f1, a1 = plt.subplots(figsize=(10, 5))
        results.plot_single_server_ready_queue(a1, sid)
        f1.tight_layout()
        p1 = out_dir / f"{output_base_name}_ready_queue_{sid}.png"
        f1.savefig(p1)
        print(f"Saved: {p1}")

        # I/O queue
        f2, a2 = plt.subplots(figsize=(10, 5))
        results.plot_single_server_io_queue(a2, sid)
        f2.tight_layout()
        p2 = out_dir / f"{output_base_name}_io_queue_{sid}.png"
        f2.savefig(p2)
        print(f"Saved: {p2}")

        # RAM usage
        f3, a3 = plt.subplots(figsize=(10, 5))
        results.plot_single_server_ram(a3, sid)
        f3.tight_layout()
        p3 = out_dir / f"{output_base_name}_ram_{sid}.png"
        f3.savefig(p3)
        print(f"Saved: {p3}")


if __name__ == "__main__":
    main()
