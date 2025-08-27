"""
Run the YAML scenario with LB + 2 servers and export charts.

Scenario file:
  data/lb_two_servers_events.yml

Outputs (saved in subfolder next to this script):
  - dashboard PNG (latency + throughput)
  - per-server PNGs: ready queue, I/O queue, RAM
"""

from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import simpy

from asyncflow.metrics.analyzer import ResultsAnalyzer
from asyncflow.runtime.simulation_runner import SimulationRunner


def main() -> None:
    """Defines paths, runs the simulation, and generates all outputs."""
    # --- 1. Define paths ---
    script_dir = Path(__file__).parent
    yaml_path = script_dir.parent / "data" / "event_inj_lb.yml"

    out_dir = script_dir / "lb_two_servers_plots"
    out_dir.mkdir(exist_ok=True)  # create if missing

    output_base_name = "lb_two_servers_events"

    if not yaml_path.exists():
        msg = f"YAML configuration file not found: {yaml_path}"
        raise FileNotFoundError(msg)

    # --- 2. Run the simulation ---
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
