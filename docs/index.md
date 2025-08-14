Here’s an updated, list-style `index.md` (in English) **without any Tutorials section** and with a clear pointer to the math details in the workload samplers.

---

# AsyncFlow Documentation

AsyncFlow is a discrete-event simulator for Python async backends (FastAPI/Uvicorn–style). It builds a **digital twin** of your service—traffic, topology, and resources—so you can measure latency, throughput, queueing, RAM, and more **before** you deploy.

> ⚠️ The package README with `pip install` & a Quickstart will land after the first PyPI release.

---


## Public API (stable surface)

* **[High-Level API](api/high-level.md)** — The two entry points you’ll use most: `AsyncFlow` (builder) and `SimulationRunner` (orchestrator).
* **[Components](api/components.md)** — Public Pydantic models for topology: `Client`, `Server`, `Endpoint`, `Edge`, `LoadBalancer`, `ServerResources`.
* **[Workload](api/workload.md)** — Traffic inputs: `RqsGenerator` and `RVConfig` (random variables).
* **[Settings](api/settings.md)** — Global controls: `SimulationSettings` (duration, sampling cadence, metrics).
* **[Enums](api/enums.md)** — Optional importable enums: distributions, step kinds/ops, metric names, node/edge types, LB algorithms.

---

## How-to Guides

* **[Builder Guide](guides/builder.md)** — Programmatically assemble a `SimulationPayload` in Python with validation and examples.
* **[YAML Input Guide](guides/yaml-builder.md)** — Author scenarios in YAML: exact schema, units, constraints, runnable samples.
* **[Dev workflow Guide](guides/dev-workflow.md)** — Describes the development workflow, repository architecture, branching strategy and CI/CD for **AsyncFlow** 

---

## Internals (design & rationale)

> Prefer formal underpinnings? The **Workload Samplers** section includes mathematical details (compound Poisson–Poisson and Normal–Poisson processes, inverse-CDF gaps, truncated Gaussians).

* **[Simulation Input (contract)](internals/simulation-input.md)** — The complete `SimulationPayload` schema and all validation guarantees (graph integrity, step coherence, etc.).
* **[Simulation Runner](internals/simulation-runner.md)** — Orchestrator design; build → wire → start → run flow; sequence diagrams; extensibility hooks.
* **[Runtime & Resources](internals/runtime-and-resources.md)** — How CPU/RAM/DB are modeled with SimPy containers; decoupling of runtime logic and resources.
* **Metrics**

  * **[Time-Series Architecture](internals/metrics/time-series-architecture.md)** — Registry → runtime state → collector pipeline; why the `if key in …` guard keeps extensibility with zero hot-path cost.
* **[Workload Samplers (math)](internals/workload-samplers.md)** — Formalization of traffic generators: windowed user resampling, rate construction $\Lambda = U \cdot \text{RPM}/60$, exponential inter-arrival via inverse-CDF, latency RV constraints.

---

## Useful mental model

Every run boils down to this validated input:

```python
SimulationPayload(
  rqs_input=RqsGenerator(...),        # workload
  topology_graph=TopologyGraph(...),  # nodes & edges
  sim_settings=SimulationSettings(...),
)
```

Build it (via **Builder** or **YAML**) and hand it to `SimulationRunner` to execute and analyze.
