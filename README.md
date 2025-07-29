# **FastSim Project Overview**

## **1. Why FastSim?**

Modern async Python stacks like FastAPI + Uvicorn are incredibly fast, yet sizing them for production often involves guesswork, costly cloud load-tests, or late-stage surprises. **FastSim** fills that gap by acting as a **digital twin** of your service:

  * It **replicates** the behavior of an async event-loop in SimPy, generating the same kinds of steps (parsing, CPU work, I/O waits) that happen in real code.
  * It **models** your infrastructure primitives—CPU cores, connection pools, and rate-limiters—so you can see queue lengths, scheduling delays, resource utilization, and end-to-end latency.
  * It **outputs** the very metrics you would scrape in production (p50/p95/p99 latency, ready-queue lag, concurrency, throughput), but entirely offline, in seconds.

With FastSim, you can ask, *“What happens if traffic doubles on Black Friday?”*, *“How many cores are needed to keep p95 latency below 100 ms?”*, or *“Is our new endpoint ready for prime time?”*—and get quantitative answers **before** you deploy.

**Outcome:** Data-driven capacity planning, early performance tuning, and far fewer surprises in production.

## **2. Installation & Quick Start**

FastSim is designed to be used as a Python library.

```bash
# Installation (coming soon to PyPI)
pip install fastsim
```

**Example Usage:**

1.  Define your system topology in a `config.yml` file:

    ```yaml
    topology:
      servers:
        - id: "app-server-1"
          # ... server configuration ...
      load_balancers:
        - id: "main-lb"
          backends: ["app-server-1"]
          # ... lb configuration ...
    settings:
      duration_s: 60
    ```

2.  Run the simulation from a Python script:

    ```python
    from fastsim import run_simulation
    from fastsim.schemas import SimulationPayload

    # Load and validate configuration using Pydantic
    payload = SimulationPayload.from_yaml("config.yml")

    # Run the simulation
    results = run_simulation(payload)

    # Analyze and plot results
    results.plot_latency_distribution()
    print(results.summary())
    ```

## **3. Who Benefits & Why**

| Audience | Pain-Point Solved | FastSim Value |
| :--- | :--- | :--- |
| **Backend Engineers** | Unsure if a 4-vCPU container can survive a traffic spike. | Run *what-if* scenarios, tweak CPU cores, and get p95 latency metrics before merging code. |
| **DevOps / SRE** | Guesswork in capacity planning; high cost of over-provisioning. | Simulate 1 to N replicas to find the most cost-effective configuration that meets the SLA. |
| **ML / LLM Teams** | LLM inference cost and latency are difficult to predict. | Model the LLM step with a price and latency distribution to estimate cost-per-request. |
| **Educators / Trainers** | Students struggle to visualize event-loop internals. | Visualize GIL ready-queue lag, CPU vs. I/O steps, and the effect of blocking code. |
| **System-Design Interviewees** | Hard to quantify trade-offs in whiteboard interviews. | Prototype real-time metrics to demonstrate how your design scales and where bottlenecks lie. |

## **4. Project Structure**

The project is a standard Python library managed with Poetry.

```
fastsim/
├── documentation/
│   └── ...
├── src/
│   └── app/
│       ├── config/
│       ├── metrics/
│       ├── resources/
│       ├── runtime/
│       │   ├── actors/
│       │   └── rqs_state.py
│       ├── samplers/
│       └── schemas/
├── tests/
│   ├── unit/
│   └── integration/
├── .github/
│   └── workflows/
│       └── ci-develop.yml
├── pyproject.toml
├── poetry.lock
└── README.md
```

## **5. Development & Contribution**

We welcome contributions\! The development workflow is managed by Poetry and quality is enforced by Ruff and MyPy.

| Task | Command | Notes |
| :--- | :--- | :--- |
| **Install dependencies** | `poetry install --with dev` | Installs main and development packages. |
| **Lint & format** | `poetry run ruff check src tests` | Style and best-practice validations. |
| **Type checking** | `poetry run mypy src tests` | Static type enforcement. |
| **Run all tests** | `poetry run pytest` | Executes the full test suite. |

### **CI with GitHub Actions**

We maintain two jobs on the `develop` branch to ensure code quality:

  * **Quick (on Pull Requests):** Runs Ruff, MyPy, and unit tests for immediate feedback.
  * **Full (on pushes to `develop`):** Runs the full suite, including integration tests and code coverage reports.

This guarantees that every commit in `develop` is style-checked, type-safe, and fully tested.

## **6. Limitations – v0.1 (First Public Release)**

1.  **Network Delay Model:** Only pure transport latency is simulated. Bandwidth-related effects (e.g., payload size, link speed) are not yet accounted for.
2.  **Concurrency Model:** The simulation models a single-threaded, cooperative event-loop (like `asyncio`). Multi-process or multi-threaded parallelism is not yet supported.
3.  **CPU Core Allocation:** Every server instance is pinned to one physical CPU core. Horizontal scaling is achieved by adding more server instances, not by using multiple cores within a single process.

These constraints will be revisited in future milestones.

## **7. Documentation**

For a deeper understanding of FastSim, we recommend reading the detailed documentation located in the `/documentation` folder at the root of the project. A guided reading path is suggested within to build a comprehensive understanding of the project's vision, architecture, and technical implementation.