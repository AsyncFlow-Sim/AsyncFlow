
# AsyncFlow — Event-Loop Aware Simulator for Async Distributed Systems

Created and maintained by @GioeleB00.

[![PyPI](https://img.shields.io/pypi/v/asyncflow-sim)](https://pypi.org/project/asyncflow-sim/)
[![Python](https://img.shields.io/pypi/pyversions/asyncflow-sim)](https://pypi.org/project/asyncflow-sim/)
[![License](https://img.shields.io/github/license/AsyncFlow-Sim/AsyncFlow)](LICENSE)
[![Status](https://img.shields.io/badge/status-v0.1.0alpha-orange)](#)
[![Ruff](https://img.shields.io/badge/lint-ruff-informational)](https://github.com/astral-sh/ruff)
[![Typing](https://img.shields.io/badge/typing-mypy-blueviolet)](https://mypy-lang.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-6DA55F)](https://docs.pytest.org/)
[![SimPy](https://img.shields.io/badge/built%20with-SimPy-1f425f)](https://simpy.readthedocs.io/)

-----

AsyncFlow is a discrete-event simulator for modeling and analyzing the performance of asynchronous, distributed backend systems built with SimPy. You describe your system's topology—its servers, network links, and load balancers—and AsyncFlow simulates the entire lifecycle of requests as they move through it.

It provides a **digital twin** of your service, modeling not just the high-level architecture but also the low-level behavior of each server's **event loop**, including explicit **CPU work**, **RAM residency**, and **I/O waits**. This allows you to run realistic "what-if" scenarios that behave like production systems rather than toy benchmarks.

### What Problem Does It Solve?

Modern async stacks like FastAPI are incredibly performant, but predicting their behavior under real-world load is difficult. Capacity planning often relies on guesswork, expensive cloud-based load tests, or discovering bottlenecks only after a production failure. AsyncFlow is designed to replace that uncertainty with **data-driven forecasting**, allowing you to understand how your system will perform before you deploy a single line of code.

### How Does It Work? An Example Topology

AsyncFlow models your system as a directed graph of interconnected components. A typical setup might look like this:

![Topology at a glance](readme_img/topology.png)

### What Questions Can It Answer?

By running simulations on your defined topology, you can get quantitative answers to critical engineering questions, such as:

  * How does **p95 latency** change if active users increase from 100 to 200?
  * What is the impact on the system if the **client-to-server network latency** increases by 3ms?
  * Will a specific API endpoint—with a pipeline of parsing, RAM allocation, and database I/O—hold its **SLA at a load of 40 requests per second**?
---

## Installation

Install from PyPI: `pip install asyncflow-sim`


## Requirements

* **Python 3.12+** (tested on 3.12, 3.13)
* **OS:** Linux, macOS, or Windows
* **Installed automatically (runtime deps):**
  **SimPy** (DES engine), **NumPy**, **Matplotlib**, **Pydantic** + **pydantic-settings**, **PyYAML**.
---

## Quick Start

### 1) Define a realistic YAML

Save as `my_service.yml`.

The full YAML schema is explained in `docs/guides/yaml-input-builder.md` and validated by Pydantic models (see `docs/internals/simulation-input.md`).

```yaml
rqs_input:
  id: generator-1
  avg_active_users: { mean: 100, distribution: poisson }
  avg_request_per_minute_per_user: { mean: 100, distribution: poisson }
  user_sampling_window: 60

topology_graph:
  nodes:
    client: { id: client-1 }

    servers:
      - id: app-1
        server_resources: { cpu_cores: 1, ram_mb: 2048 }
        endpoints:
          - endpoint_name: /api
            # Realistic pipeline on one async server:
            # - 2 ms CPU parsing (blocks the event loop)
            # - 120 MB RAM working set (held until the request leaves the server)
            # - 12 ms DB-like I/O (non-blocking wait)
            steps:
              - kind: initial_parsing
                step_operation: { cpu_time: 0.002 }
              - kind: ram
                step_operation: { necessary_ram: 120 }
              - kind: io_db
                step_operation: { io_waiting_time: 0.012 }

  edges:
    - { id: gen-client,   source: generator-1, target: client-1,
        latency: { mean: 0.003, distribution: exponential } }
    - { id: client-app,   source: client-1,   target: app-1,
        latency: { mean: 0.003, distribution: exponential } }
    - { id: app-client,   source: app-1,      target: client-1,
        latency: { mean: 0.003, distribution: exponential } }

sim_settings:
  total_simulation_time: 300
  sample_period_s: 0.05
  enabled_sample_metrics:
    - ready_queue_len
    - event_loop_io_sleep
    - ram_in_use
    - edge_concurrent_connection
  enabled_event_metrics:
    - rqs_clock
```

Prefer building scenarios in Python? There’s a Python builder with the same semantics (create nodes, edges, endpoints programmatically). See **`docs/guides/python-builder.md`**.

### 2) Run and export charts

Save as `run_my_service.py`.

```python
from __future__ import annotations

from pathlib import Path
import simpy
import matplotlib.pyplot as plt

from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer


def main() -> None:
    script_dir = Path(__file__).parent
    yaml_path = script_dir / "my_service.yml"
    out_path = script_dir / "my_service_plots.png"

    env = simpy.Environment()
    runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
    res: ResultsAnalyzer = runner.run()

    # Print a concise latency summary
    print(res.format_latency_stats())

    # 2x2: Latency | Throughput | Ready (first server) | RAM (first server)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=160)

    res.plot_latency_distribution(axes[0, 0])
    res.plot_throughput(axes[0, 1])

    sids = res.list_server_ids()
    if sids:
        sid = sids[0]
        res.plot_single_server_ready_queue(axes[1, 0], sid)
        res.plot_single_server_ram(axes[1, 1], sid)
    else:
        for ax in (axes[1, 0], axes[1, 1]):
            ax.text(0.5, 0.5, "No servers", ha="center", va="center")
            ax.axis("off")

    fig.tight_layout()
    fig.savefig(out_path)
    print(f"Plots saved to: {out_path}")


if __name__ == "__main__":
    main()

```

Run the python script

You’ll get latency stats in the terminal and a PNG with four charts (latency distribution, throughput, server queues, RAM usage).

**Want more?** 

For ready-to-run scenarios—including examples using the Pythonic builder and multi-server topologies—check out the `examples/` directory in the repository.

## Development

If you want to contribute or run the full test suite locally, follow these steps.

### Requirements

* **Python 3.12+** (tested on 3.12, 3.13)
* **OS:** Linux, macOS, or Windows
* **Runtime deps installed by the package:** SimPy, NumPy, Matplotlib, Pydantic, PyYAML, pydantic-settings

**Prerequisites:** Git, Python 3.12+ in `PATH`, `curl` (Linux/macOS/WSL), PowerShell 7+ (Windows)

---

## Project setup

```bash
git clone https://github.com/AsyncFlow-Sim/AsyncFlow.git
cd AsyncFlow
```

From the repo root, run the **one-shot post-clone setup**:

**Linux / macOS / WSL**

```bash
bash scripts/dev_setup.sh
```

**Windows (PowerShell)**

```powershell
# If scripts are blocked by policy, run this in the same PowerShell session:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\dev_setup.ps1
```

**What this does (concise):**

* Ensures **Poetry** is available (installs if missing).
* Uses a **project-local `.venv`**.
* Removes `poetry.lock` for a **clean dependency resolve** (dev policy).
* Installs the project **with dev extras**.
* Runs **ruff**, **mypy**, and **pytest (with coverage)**.

**Quick sanity check after setup:**

```bash
poetry --version
poetry run python -V
```

> **Note (lock policy):** `dev_setup` intentionally removes `poetry.lock` to avoid cross-platform conflicts during development.

**Scripts (for quick access):**

* [`scripts/dev_setup.sh`](scripts/dev_setup.sh) / [`scripts/dev_setup.ps1`](scripts/dev_setup.ps1)
* [`scripts/quality_check.sh`](scripts/quality_check.sh) / [`scripts/quality_check.ps1`](scripts/quality_check.ps1)
* [`scripts/run_tests.sh`](scripts/run_tests.sh) / [`scripts/run_tests.ps1`](scripts/run_tests.ps1)

---

### Handy scripts (after setup)

#### 1) Lint + type check

**Linux / macOS / WSL**

```bash
bash scripts/quality_check.sh
```

**Windows (PowerShell)**

```powershell
.\scripts\quality_check.ps1
```

Runs **ruff** (lint/format check) and **mypy** on `src` and `tests`.

#### 2) Run tests with coverage (unit + integration)

**Linux / macOS / WSL**

```bash
bash scripts/run_tests.sh
```

**Windows (PowerShell)**

```powershell
.\scripts\run_tests.ps1
```

#### 3) Run system tests

**Linux / macOS / WSL**

```bash
bash scripts/run_sys_tests.sh
```

**Windows (PowerShell)**

```powershell
.\scripts\run_sys_tests.ps1
```

Executes **pytest** with a terminal coverage summary (no XML, no slowest list).



## What AsyncFlow Models (v0.1)

AsyncFlow provides a detailed simulation of your backend system. Here is a high-level overview of the core components it models. For a deeper technical dive into the implementation and design rationale, follow the links to the internal documentation.

* **Async Event Loop:** Simulates a single-threaded, non-blocking event loop per server. **CPU steps** block the loop, while **I/O steps** are non-blocking, accurately modeling `asyncio` behavior.
    * *(Deep Dive: `docs/internals/runtime-and-resources.md`)*

* **System Resources:** Models finite server resources, including **CPU cores** and **RAM (MB)**. Requests must acquire these resources, creating natural back-pressure and contention when the system is under load.
    * *(Deep Dive: `docs/internals/runtime-and-resources.md`)*

* **Endpoints & Request Lifecycles:** Models server endpoints as a linear sequence of **steps**. Each step is a distinct operation, such as `cpu_bound_operation`, `io_wait`, or `ram` allocation.
    * *(Schema Definition: `docs/internals/simulation-input.md`)*

* **Network Edges:** Simulates the connections between system components. Each edge has a configurable **latency** (drawn from a probability distribution) and an optional **dropout rate** to model packet loss.
    * *(Schema Definition: `docs/internals/simulation-input.md` | Runtime Behavior: `docs/internals/runtime-and-resources.md`)*

* **Stochastic Workload:** Generates user traffic based on a two-stage sampling model, combining the number of active users and their request rate per minute to produce a realistic, fluctuating load (RPS) on the system.
    * *(Modeling Details with mathematical explanation and clear assumptions: `docs/internals/requests-generator.md`)*

* **Metrics & Outputs:** Collects two types of data: **time-series metrics** (e.g., `ready_queue_len`, `ram_in_use`) and **event-based data** (`RqsClock`). This raw data is used to calculate final KPIs like **p95/p99 latency** and **throughput**.
    * *(Metric Reference: `docs/internals/metrics`)*

## Current Limitations (v0.1)

* Network realism: base latency + optional drops (no bandwidth/payload/TCP yet).
* Single event loop per server: no multi-process/multi-node servers yet.
* Linear endpoint flows: no branching/fan-out within an endpoint.
* No thread-level concurrency; modeling OS threads and scheduler/context switching is out of scope.”
* Stationary workload: no diurnal patterns or feedback/backpressure.
* Sampling cadence: very short spikes can be missed if `sample_period_s` is large.


## Roadmap (Order is not indicative of priority)

This roadmap outlines the key development areas to transform AsyncFlow into a comprehensive framework for statistical analysis and resilience modeling of distributed systems.

### 1. Monte Carlo Simulation Engine

**Why:** To overcome the limitations of a single simulation run and obtain statistically robust results. This transforms the simulator from an "intuition" tool into an engineering tool for data-driven decisions with confidence intervals.

* **Independent Replications:** Run the same simulation N times with different random seeds to sample the space of possible outcomes.
* **Warm-up Period Management:** Introduce a "warm-up" period to be discarded from the analysis, ensuring that metrics are calculated only on the steady-state portion of the simulation.
* **Ensemble Aggregation:** Calculate means, standard deviations, and confidence intervals for aggregated metrics (latency, throughput) across all replications.
* **Confidence Bands:** Visualize time-series data (e.g., queue lengths) with confidence bands to show variability over time.

### 2. Realistic Service Times (Stochastic Service Times)

**Why:** Constant service times underestimate tail latencies (p95/p99), which are almost always driven by "slow" requests. Modeling this variability is crucial for a realistic analysis of bottlenecks.

* **Distributions for Steps:** Allow parameters like `cpu_time` and `io_waiting_time` in an `EndpointStep` to be sampled from statistical distributions (e.g., Lognormal, Gamma, Weibull) instead of being fixed values.
* **Per-Request Sampling:** Each request will sample its own service times independently, simulating the natural variability of a real-world system.

### 3. Component Library Expansion

**Why:** To increase the variety and realism of the architectures that can be modeled.

* **New System Nodes:**
    * `CacheRuntime`: To model caching layers (e.g., Redis) with hit/miss logic, TTL, and warm-up behavior.
    * `APIGatewayRuntime`: To simulate API Gateways with features like rate-limiting and authentication caching.
    * `DBRuntime`: A more advanced model for databases featuring connection pool contention and row-level locking.
* **New Load Balancer Algorithms:** Add more advanced routing strategies (e.g., Weighted Round Robin, Least Response Time).

### 4. Fault and Event Injection

**Why:** To test the resilience and behavior of the system under non-ideal conditions, a fundamental use case for Site Reliability Engineering (SRE).

* **API for Scheduled Events:** Introduce a system to schedule events at specific simulation times, such as:
    * **Node Down/Up:** Turn a server off and on to test the load balancer's failover logic.
    * **Degraded Edge:** Drastically increase the latency or drop rate of a network link.
    * **Error Bursts:** Simulate a temporary increase in the rate of application errors.

### 5. Advanced Network Modeling

**Why:** To more faithfully model network-related bottlenecks that are not solely dependent on latency.

* **Bandwidth and Payload Size:** Introduce the concepts of link bandwidth and request/response size to simulate delays caused by data transfer.
* **Retries and Timeouts:** Model retry and timeout logic at the client or internal service level.

### 6. Complex Endpoint Flows

**Why:** To model more realistic business logic that does not follow a linear path.

* **Conditional Branching:** Introduce the ability to have conditional steps within an endpoint (e.g., a different path for a cache hit vs. a cache miss).
* **Fan-out / Fan-in:** Model scenarios where a service calls multiple downstream services in parallel and waits for their responses.

### 7. Backpressure and Autoscaling

**Why:** To simulate the behavior of modern, adaptive systems that react to load.

* **Dynamic Rate Limiting:** Introduce backpressure mechanisms where services slow down the acceptance of new requests if their internal queues exceed a certain threshold.
* **Autoscaling Policies:** Model simple Horizontal Pod Autoscaler (HPA) policies where the number of server replicas increases or decreases based on metrics like CPU utilization or queue length.

