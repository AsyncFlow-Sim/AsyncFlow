# **AsyncFlow – Event-Loop Aware Simulation for Backend Systems**

## **1. Overview**

Modern asynchronous Python stacks such as **FastAPI + Uvicorn** deliver impressive performance, yet capacity planning for production workloads often relies on guesswork, costly cloud-based load tests, or late-stage troubleshooting.

**AsyncFlow** addresses this challenge by providing a **digital twin** of your service that can be run entirely offline. It models event-loop behaviour, resource constraints, and request lifecycles, enabling you to forecast performance under different workloads and architectural choices **before deployment**.

AsyncFlow allows you to answer questions such as:

* *What happens to p95 latency if traffic doubles during a peak event?*
* *How many cores are required to maintain SLAs at scale?*
* *What is the cost-per-request of adding a large language model (LLM) inference step?*

The simulation outputs metrics identical in form to those collected in production—such as p50/p95/p99 latency, concurrency, resource utilisation, and throughput—making results directly actionable.

**Outcome:** Data-driven capacity planning, early performance tuning, and reduced operational surprises.

---

## **2. Key Features**

* **Event-loop accuracy** – Models a single-threaded asynchronous runtime, including CPU-bound work, I/O waits, and parsing.
* **Resource modelling** – Simulates CPU cores, memory, connection pools, and rate limiters as discrete resources.
* **Network simulation** – Models transport latency per edge in the system topology.
* **Workload flexibility** – Supports stochastic arrival processes (e.g., Poisson, Normal) for user traffic generation.
* **Metrics parity with production** – Produces time-series and event-level metrics aligned with observability tools.
* **Offline and repeatable** – No need for costly cloud infrastructure to conduct performance tests.

---

## **3. Installation**

Until published, clone the repository and install in editable mode:

### Requirements
- Python 3.11+ (recommended 3.12)
- Poetry ≥ 1.6

AsyncFlow uses [Poetry](https://python-poetry.org/) for dependency management.
If you do not have Poetry installed, follow these steps.

### 3.1 Install Poetry (official method)

**Linux / macOS**

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

**Windows (PowerShell)**

```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

> **Note:** Ensure that Poetry’s binary directory is in your `PATH`.
> On Linux/macOS this is typically `~/.local/bin`;
> on Windows it is `%APPDATA%\Python\Scripts` or the path printed at the end of installation.

---

### 3.2 Clone the repository and set up a local virtual environment

```bash
# Clone the repository
git clone https://github.com/GioeleB00/AsyncFlow-Backend.git
cd AsyncFlow-Backend

# Configure Poetry to always create a local `.venv` inside the project
poetry config virtualenvs.in-project true

# Install all dependencies (main + dev) inside the local venv
poetry install --with dev
```

After this step, you will see a `.venv/` directory inside the project root.
To activate the environment manually:

```bash
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows
```

Or simply run commands via Poetry without manual activation, for example:

```bash
poetry run pytest
poetry run python examples/single_server.py
```

---

## **4. Quick Start**

### 1. Define your simulation payload

Go to the folder `/examples` open the file `single_server.py`
and run it from the terminal, you will see the output of the system
described in `/examples/data/single_server.yml` and you will see a 
`.png` file with different plots.

If you want to build your own configuration, read the guide in the `/docs` folder on how to craft a `.yml` input correctly.

```yaml
rqs_input:
  id: generator-1
  avg_active_users:
    mean: 100
    distribution: poisson
  avg_request_per_minute_per_user:
    mean: 20
    distribution: poisson
  user_sampling_window: 60

topology_graph:
  nodes:
    client:
      id: client-1
      type: client
    servers:
      - id: app-server-1
        type: server
        server_resources:
          cpu_cores: 2
          ram_mb: 2048
        endpoints:
          - endpoint_name: /predict
            steps:
              - kind: ram
                step_operation: { necessary_ram: 100 }
              - kind: cpu
                step_operation: { cpu_time: 0.005 }
  edges:
    - id: gen-to-client
      source: generator-1
      target: client-1
      latency: { mean: 0.003, distribution: exponential }
    - id: client-to-server
      source: client-1
      target: app-server-1
      latency: { mean: 0.003, distribution: exponential }
    - id: server-to-client
      source: app-server-1
      target: client-1
      latency: { mean: 0.003, distribution: exponential }

sim_settings:
  total_simulation_time: 300
  sample_period_s: 0.05
  enabled_sample_metrics:
    - ready_queue_len
    - ram_in_use
  enabled_event_metrics:
    - rqs_clock
```

and add it to the `/examples/data` folder

### 2. Run the simulation

build a python file in the `/examples` folder and copy the 
following script replacing `<your_file_name>` with the 
real name


```python

from pathlib import Path

import simpy
import matplotlib.pyplot as plt

from asyncflow.config.constants import LatencyKey
from asyncflow.runtime.simulation_runner import SimulationRunner
from asyncflow.metrics.analyzer import ResultsAnalyzer

def print_latency_stats(res: ResultsAnalyzer) -> None:
    """Print latency statistics returned by the analyzer."""
    stats = res.get_latency_stats()
    print("\n=== LATENCY STATS ===")
    if not stats:
        print("(empty)")
        return

    order: list[LatencyKey] = [
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

def save_all_plots(res: ResultsAnalyzer, out_path: Path) -> None:
    """Generate the 2x2 plot figure and save it to `out_path`."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    res.plot_latency_distribution(axes[0, 0])
    res.plot_throughput(axes[0, 1])
    res.plot_server_queues(axes[1, 0])
    res.plot_ram_usage(axes[1, 1])
    fig.tight_layout()
    fig.savefig(out_path)
    print(f"Plots saved to: {out_path}")

# Paths
yaml_path = Path(__file__).parent / "data" /"<your_file_name>.yml"
out_path = Path(__file__).parent / "<your_file_name>_plots.png"

# Simulation
env = simpy.Environment()
runner = SimulationRunner.from_yaml(env=env, yaml_path=yaml_path)
results: ResultsAnalyzer = runner.run()

# Output
print_latency_stats(results)
save_all_plots(results, out_path)

```
run the script and you will see the different plots and on your terminal
you will see the latency stats

---

## **5. Target Users and Use Cases**

| Audience                 | Challenge                                         | AsyncFlow Value                                                                    |
| ------------------------ | ------------------------------------------------- | -------------------------------------------------------------------------------- |
| Backend Engineers        | Sizing services for variable workloads            | Model endpoint workflows and resource bottlenecks before deployment              |
| DevOps / SRE             | Balancing cost and SLA                            | Simulate scaling scenarios to choose optimal capacity                            |
| ML / LLM Teams           | Unclear latency/cost impact of inference steps    | Integrate stochastic inference times and cost models into the service simulation |
| Educators                | Explaining async runtime internals                | Demonstrate queueing, blocking effects, and CPU vs. I/O trade-offs               |
| System Design Candidates | Quantifying architecture trade-offs in interviews | Prototype a simulated design to visualise scalability and bottlenecks            |

---

## **6. Project Structure**

The project follows a standard Python package layout, managed with Poetry.

```
AsyncFlow-Backend/
├── examples/                # Examples payloads and datasets
├── scripts/                 # Utility scripts (linting, startup)
├── docs/                    # Project vision and technical documentation
├── tests/                   # Unit and integration tests
├── src/
│   └── app/
│       ├── config/          # Settings and constants
│       ├── metrics/         # KPI computation and aggregation
│       ├── resources/       # SimPy resource registry
│       ├── runtime/         # Simulation core and actors
│       ├── samplers/        # Random variable generators
│       └── schemas/         # Pydantic models for validation
├── pyproject.toml
└── README.md
```

---

## **7. Development Workflow**

AsyncFlow uses **Poetry** for dependency management and enforces quality via **Ruff** and **MyPy**.

| Task          | Command                           | Description                            |
| ------------- | --------------------------------- | -------------------------------------- |
| Install deps  | `poetry install --with dev`       | Main and development dependencies      |
| Lint & format | `poetry run ruff check src tests` | Style and best-practice checks         |
| Type checking | `poetry run mypy src tests`       | Static type enforcement                |
| Run tests     | `poetry run pytest`               | Execute all unit and integration tests |

---

## **8. Continuous Integration**

The GitHub Actions pipeline enforces:

* **Pull Requests:** Ruff, MyPy, and unit tests for rapid feedback.
* **Develop branch:** Full suite including integration tests and coverage reporting.

No code is merged without passing all checks, ensuring maintainability and reliability.

---

## **9. Current Limitations (v0.1)**

1. **Network delay model** – Bandwidth effects and payload size are not yet considered.
2. **Concurrency model** – Single-threaded async event-loop; no native multi-thread or multi-process simulation.
3. **CPU allocation** – One process per server instance; multi-core within a process is not yet modelled.

In addition to the items already listed (simplified network delay, single-threaded async model, and one process per server), keep in mind:

* **Stationary, independent workload.** Traffic is sampled from stationary distributions; there is no diurnal seasonality, burst shaping, or feedback coupling (e.g., servers slowing down arrivals). Average users and per-user RPM are sampled independently.
* **Simplified request flow.** Endpoints execute a linear sequence of steps; there is no conditional branching/fan-out within an endpoint (e.g., cache hit/miss paths, error paths) and no per-request control flow.
* **Network realism is limited.** Beyond base latency and optional drops, the model does not account for payload size, bandwidth constraints, TCP behavior (slow start, congestion), retries/timeouts, or jitter.
* **No backpressure or autoscaling.** The generator does not adapt to server state (queues, errors), and there is no policy loop for rate limiting or scaling during the run.
* **Telemetry granularity.** Sampled metrics are collected at a fixed `sample_period_s` and may miss very short-lived spikes unless you lower the period (at a runtime cost). Event resolution itself is not affected by the sampling period.
* **Reproducibility.** Unless you fix a random seed (not yet exposed in all entry points), repeated runs will vary within the chosen distributions.

---

## Mini Roadmap

Short, high-impact items we plan to add next:

1. **Cache modeling.** First-class cache layers (per-endpoint hit/miss with TTL and warm-up), configurable hit-ratio profiles, and their effect on latency, CPU, and RAM.
2. **LLM inference as a step + cost accounting.** Treat inference as a dedicated endpoint step with its own latency distribution, concurrency limits/batching, and per-request cost model (tokens, provider pricing).
3. **Fault and event injection.** Time-based events (node down/up, degraded edge, error-rate spikes) with deterministic timelines to test resilience and recovery.
4. **Network bandwidth & payload size.** Throughput-aware links, request/response sizes, retries/timeouts, and simple congestion effects.
5. **Branching/control-flow within endpoints.** Conditional steps (e.g., cache hit vs. miss), probabilistic routing, and fan-out/fan-in to external services.
6. **Backpressure and autoscaling loops.** Rate limiting tied to queue depth/latency SLOs and simple scale-up/down policies during a run.


Future milestones will extend these capabilities.

---

## **10. Documentation**

Comprehensive documentation is available in the `/docs` directory, covering:

* Simulation model and architecture
* Schema definitions
* Example scenarios
* Extension guidelines
* Guide to build valid .yaml as valid simulation input

---
