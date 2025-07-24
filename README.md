Certamente. Ecco il contenuto del `README.md` visualizzato direttamente qui.

-----

# **FastSim Project Overview**

## **1. Why FastSim?**

FastAPI + Uvicorn gives Python teams a lightning-fast async stack, yet sizing it for production still means guesswork, costly cloud load-tests, or late surprises. **FastSim** fills that gap by becoming a **digital twin** of your actual service:

  * It **replicates** your FastAPI + Uvicorn event-loop behavior in SimPy, generating the same kinds of asynchronous steps (parsing, CPU work, I/O, LLM calls) that happen in real code.
  * It **models** your infrastructure primitives—CPU cores (via a SimPy `Resource`), database pools, rate-limiters, and even GPU inference quotas—so you can see queue lengths, scheduling delays, resource utilization, and end-to-end latency.
  * It **outputs** the very metrics you would scrape in production (p50/p95/p99 latency, ready-queue lag, concurrency, throughput, cost per LLM call), but entirely offline, in seconds.

With FastSim you can ask, *“What happens if traffic doubles on Black Friday?”*, *“How many cores are needed to keep p95 latency below 100 ms?”*, or *“Is our LLM-driven endpoint ready for prime time?”*—and get quantitative answers **before** you deploy.

**Outcome:** Data-driven capacity planning, early performance tuning, and far fewer surprises in production.

## **2. Project Goals**

| \# | Goal | Practical Outcome |
| :--- | :--- | :--- |
| 1 | **Pre-production sizing** | Know the required core count, pool size, and replica count to meet your SLA. |
| 2 | **Scenario analysis** | Explore various traffic models, endpoint mixes, latency distributions, and RTT. |
| 3 | **Twin metrics** | Produce the same metrics you’ll scrape in production (latency, queue length, CPU utilization). |
| 4 | **Rapid iteration** | A single YAML/JSON configuration or REST call generates a full performance report. |
| 5 | **Educational value** | Visualize how GIL contention, queue length, and concurrency react to load. |

## **3. Who Benefits & Why**

| Audience | Pain-Point Solved | FastSim Value |
| :--- | :--- | :--- |
| **Backend Engineers** | Unsure if a 4-vCPU container can survive a marketing traffic spike. | Run *what-if* scenarios, tweak CPU cores or pool sizes, and get p95 latency and max-concurrency metrics before merging code. |
| **DevOps / SRE** | Guesswork in capacity planning; high cost of over-provisioning. | Simulate 1 to N replicas, autoscaler thresholds, and database pool sizes to find the most cost-effective configuration that meets the SLA. |
| **ML / LLM Product Teams** | LLM inference cost and latency are difficult to predict. | Model the LLM step with a price and latency distribution to estimate cost-per-request and the benefits of GPU batching without needing real GPUs. |
| **Educators / Trainers** | Students struggle to visualize event-loop internals. | Visualize GIL ready-queue lag, CPU vs. I/O steps, and the effect of blocking code—perfect for live demos and labs. |
| **Consultants / Architects** | Need a quick proof-of-concept for new client designs. | Define endpoints in YAML and demonstrate throughput and latency under projected load in minutes. |
| **Open-Source Community** | Lacks a lightweight Python simulator for ASGI workloads. | An extensible codebase makes it easy to plug in new resources (e.g., rate-limiters, caches) or traffic models (e.g., spike, uniform ramp). |
| **System-Design Interviewees** | Hard to quantify trade-offs in whiteboard interviews. | Prototype real-time metrics—queue lengths, concurrency, latency distributions—to demonstrate how your design scales and where bottlenecks lie. |

## **4. About This Documentation**

This project contains extensive documentation covering its vision, architecture, and technical implementation. The documents are designed to be read in sequence to build a comprehensive understanding of the project.

### **How to Read This Documentation**

For the best understanding of FastSim, we recommend reading the documentation in the following order:

1.  **README.md (This Document)**: Start here for a high-level overview of the project's purpose, goals, target audience, and development workflow. It provides the essential context for all other documents.
2.  **dev_worflow_guide**: This document details the github workflow for the development
3.  **simulation_input**: This document details the technical contract for configuring a simulation. It explains the `SimulationPayload` and its components (`rqs_input`, `topology_graph`, `sim_settings`). This is essential reading for anyone who will be creating or modifying simulation configurations.
4.  **runtime_and_resources**: A deep dive into the simulation's internal engine. It explains how the validated input is transformed into live SimPy processes (Actors, Resources, State). This is intended for advanced users or contributors who want to understand *how* the simulation works under the hood.
5.  **requests_generator**: This document covers the mathematical and algorithmic details behind the traffic generation model. It is for those interested in the statistical foundations of the simulator.
6.  **Simulation Metrics**: A comprehensive guide to all output metrics. It explains what each metric measures, how it's collected, and why it's important for performance analysis.

Optional **fastsim_vision**: a more detailed document about the project vision

you can find the documentation at the root of the project in the folder `documentation/`

## **5. Development Workflow & Architecture Guide**

This section outlines the standardized development workflow, repository architecture, and branching strategy for the FastSim backend.

### **Technology Stack**

  * **Backend**: FastAPI
  * **Backend Package Manager**: Poetry
  * **Frontend**: React + JavaScript
  * **Database**: PostgreSQL
  * **Caching**: Redis
  * **Containerization**: Docker

### **Backend Service (`FastSim-backend`)**

The repository hosts the entire FastAPI backend, which exposes the REST API, runs the discrete-event simulation, communicates with the database, and provides metrics.

```
fastsim-backend/
├── Dockerfile
├── docker_fs/
│   ├── docker-compose.dev.yml
│   └── docker-compose.prod.yml
├── scripts/
│   ├── init-docker-dev.sh
│   └── quality-check.sh
├── alembic/
│   ├── env.py
│   └── versions/
├── documentation/
│   └── backend_documentation/
├── tests/
│   ├── unit/
│   └── integration/
├── src/
│   └── app/
│       ├── api/
│       ├── config/
│       ├── db/
│       ├── metrics/
│       ├── resources/
│       ├── runtime/
│       │   ├── rqs_state.py
│       │   └── actors/
│       ├── samplers/
│       ├── schemas/
│       ├── main.py
│       └── simulation_run.py
├── poetry.lock
├── pyproject.toml
└── README.md
```

### **How to Start the Backend with Docker (Development)**

To spin up the backend and its supporting services in development mode:

1.  **Install & run Docker** on your machine.
2.  **Clone** the repository and `cd` into its root.
3.  Execute:
    ```bash
    bash ./scripts/init-docker-dev.sh
    ```
    This will launch a **PostgreSQL** container and a **Backend** container that mounts your local `src/` folder with live-reload enabled.

### **Development Architecture & Philosophy**

We split responsibilities between Docker-managed services and local workflows.

  * **Docker-Compose for Development**: Containers host external services (PostgreSQL) and run the FastAPI app. Your local `src/` directory is mounted into the backend container for hot-reloading. No tests, migrations, or linting run inside these containers during development.
  * **Local Quality & Testing Workflow**: All code quality tools, migrations, and tests are executed on your host machine for faster feedback and full IDE support.

| Task | Command | Notes |
| :--- | :--- | :--- |
| **Lint & format** | `poetry run ruff check src tests` | Style and best-practice validations |
| **Type checking** | `poetry run mypy src tests` | Static type enforcement |
| **Unit tests** | `poetry run pytest -m "not integration"` | Fast, isolated tests—no DB required |
| **Integration tests** | `poetry run pytest -m integration` | Real-DB tests against Docker’s PostgreSQL |
| **DB migrations** | `poetry run alembic upgrade head` | Applies migrations to your local Docker-hosted DB |

**Rationale**: Running tests or Alembic migrations inside Docker images would slow down your feedback loop and limit IDE features by requiring you to mount the full source tree and install dev dependencies in each build.

## **6. CI/CD with GitHub Actions**

We maintain two jobs on the `develop` branch to ensure code quality and stability.

### **Quick (on Pull Requests)**

  * Ruff & MyPy checks
  * Unit tests only
  * **No database required**

### **Full (on pushes to `develop`)**

  * All checks from the "Quick" suite
  * Starts a **PostgreSQL** service container
  * Runs **Alembic** migrations
  * Executes the **full test suite** (unit + integration)
  * Builds the **Docker** image
  * **Smoke-tests** the `/health` endpoint of the built container

**Guarantee**: Every commit in `develop` is style-checked, type-safe, database-tested, and Docker-ready.

## **7. Limitations – v0.1 (First Public Release)**

1.  **Network Delay Model**
      * Only pure transport latency is simulated.
      * Bandwidth-related effects (e.g., payload size, link speed, congestion) are NOT accounted for.
2.  **Concurrency Model**
      * The service exposes **async-only endpoints**.
      * Execution runs on a single `asyncio` event-loop thread.
      * No thread-pool workers or multi-process setups are supported yet; therefore, concurrency is limited to coroutine scheduling (cooperative, single-thread).
3.  **CPU Core Allocation**
      * Every server instance is pinned to **one physical CPU core**.
      * Horizontal scaling must be achieved via multiple containers/VMs, not via multi-core utilization inside a single process.

These constraints will be revisited in future milestones once kernel-level context-switching costs, I/O bandwidth modeling, and multi-process orchestration are integrated.