# AsyncFlow – Programmatic Input Guide (builder)

This guide shows how to **build the full simulation input in Python** using the
`AsyncFlow` builder, with the same precision and validation guarantees as the YAML flow.
You’ll see **all components, valid values, units, constraints, and how validation is enforced**.

Under the hood, the builder assembles a single `SimulationPayload`:

```python
SimulationPayload(
    rqs_input=RqsGenerator(...),          # traffic generator (workload)
    topology_graph=TopologyGraph(...),    # system as a graph
    sim_settings=SimulationSettings(...), # global settings and metrics
)
```

Everything is **validated up front** by Pydantic. If something is inconsistent
(e.g., an edge points to a non-existent node), a clear error is raised
**before** running the simulation.

---

## Quick Start (Minimal Example)

```python
from __future__ import annotations

import simpy

# Public, user-facing API
from asyncflow import AsyncFlow, SimulationRunner
from asyncflow.components import (
    RqsGenerator, SimulationSettings, Endpoint, Client, Server, Edge
)
from asyncflow.schemas.payload import SimulationPayload  # optional, for typing

# 1) Workload
generator = RqsGenerator(
    id="rqs-1",
    avg_active_users={"mean": 50, "distribution": "poisson"},
    avg_request_per_minute_per_user={"mean": 30, "distribution": "poisson"},
    user_sampling_window=60,  # seconds
)

# 2) Nodes (client + one server)
client = Client(id="client-1")
endpoint = Endpoint(
    endpoint_name="/hello",
    steps=[
        {"kind": "ram",              "step_operation": {"necessary_ram": 32}},
        {"kind": "initial_parsing",  "step_operation": {"cpu_time": 0.002}},
        {"kind": "io_wait",          "step_operation": {"io_waiting_time": 0.010}},
    ],
)
server = Server(
    id="srv-1",
    server_resources={"cpu_cores": 1, "ram_mb": 1024},
    endpoints=[endpoint],
)

# 3) Edges (directed, with latency as RV)
edges = [
    Edge(
        id="gen-to-client",
        source="rqs-1",                # external sources allowed
        target="client-1",             # targets must be declared nodes
        latency={"mean": 0.003, "distribution": "exponential"},
    ),
    Edge(
        id="client-to-server",
        source="client-1",
        target="srv-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    ),
    Edge(
        id="server-to-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    ),
]

# 4) Global settings
settings = SimulationSettings(
    total_simulation_time=300,   # seconds, min 5
    sample_period_s=0.01,        # seconds, [0.001 .. 0.1]
    enabled_sample_metrics=[
        "ready_queue_len",
        "event_loop_io_sleep",
        "ram_in_use",
        "edge_concurrent_connection",
    ],
    enabled_event_metrics=["rqs_clock"],
)

# 5) Build (validates everything)
payload: SimulationPayload = (
    AsyncFlow()
    .add_generator(generator)
    .add_client(client)
    .add_servers(server)      # varargs; supports multiple
    .add_edges(*edges)        # varargs; supports multiple
    # .add_load_balancer(lb)  # optional
    .add_simulation_settings(settings)
    .build_payload()
)

# 6) Run
env = simpy.Environment()
results = SimulationRunner(env=env, simulation_input=payload).run()
```

---

## 1) Random Variables (`RVConfig`)

Where a parameter is stochastic (e.g., edge latency, users, RPM), you pass a
dictionary that Pydantic converts into an `RVConfig`:

```python
{"mean": <float>, "distribution": <enum>, "variance": <float?>}
```

### Supported distributions

* `"poisson"`
* `"normal"`
* `"log_normal"`
* `"exponential"`
* `"uniform"`

### Rules & defaults

* `mean` is **required** and numeric; coerced to `float`.
* If `distribution` is `"normal"` or `"log_normal"` and `variance` is absent,
  it defaults to **`variance = mean`**.
* For **edge latency**: **`mean > 0`** and, if provided, **`variance ≥ 0`**.

**Units**

* Time values are **seconds**.
* Rates are **requests per minute** (where noted).

---

## 2) Workload: `RqsGenerator`

```python
from asyncflow.components import RqsGenerator

generator = RqsGenerator(
    id="rqs-1",
    avg_active_users={
        "mean": 100,
        "distribution": "poisson",  # or "normal"
        # "variance": <float>,       # optional; auto=mean if "normal"
    },
    avg_request_per_minute_per_user={
        "mean": 20,
        "distribution": "poisson",  # must be poisson in current samplers
    },
    user_sampling_window=60,        # [1 .. 120] seconds
)
```

**Semantics**

* `avg_active_users`: active users as a random variable (**Poisson** or **Normal**).
* `avg_request_per_minute_per_user`: per-user RPM (**Poisson** only).
* `user_sampling_window`: re-sample active users every N seconds.

---

## 3) System Topology (`Client`, `Server`, `LoadBalancer`, `Edge`)

Represent the system as a **directed graph**: nodes (client, servers, optional
LB) and edges (network links).

### 3.1 Client

```python
from asyncflow.components import Client

client = Client(id="client-1")  # type is fixed to 'client'
```

### 3.2 Server & Endpoints

```python
from asyncflow.components import Endpoint, Server

endpoint = Endpoint(
    endpoint_name="/api",   # normalized to lowercase internally
    steps=[
        {"kind": "ram",                 "step_operation": {"necessary_ram": 64}},
        {"kind": "cpu_bound_operation", "step_operation": {"cpu_time": 0.004}},
        {"kind": "io_db",               "step_operation": {"io_waiting_time": 0.012}},
    ],
)

server = Server(
    id="srv-1",  # type fixed to 'server'
    server_resources={
        "cpu_cores": 2,       # int ≥ 1
        "ram_mb": 2048,       # int ≥ 256
        "db_connection_pool": None,  # optional
    },
    endpoints=[endpoint],
)
```

**Step kinds** (enums)

* **CPU**: `"initial_parsing"`, `"cpu_bound_operation"`
* **RAM**: `"ram"`
* **I/O**: `"io_task_spawn"`, `"io_llm"`, `"io_wait"`, `"io_db"`, `"io_cache"`

**Operation keys** (enum `StepOperation`)

* `cpu_time` (seconds, positive)
* `necessary_ram` (MB, positive int/float)
* `io_waiting_time` (seconds, positive)

**Validation enforced**

* Each step’s `step_operation` has **exactly one** entry.
* The operation **must match** the step kind.
* All numeric values **> 0**.

**Runtime semantics (high level)**

* RAM is reserved before CPU, then released at the end.
* CPU tokens are acquired for CPU-bound segments; released when switching to I/O.
* I/O waits **do not** hold a CPU core.

### 3.3 Load Balancer (optional)

```python
from asyncflow.schemas.topology.nodes import LoadBalancer  # internal type
# (Use only if you build the graph manually. AsyncFlow builder hides the graph.)

lb = LoadBalancer(
    id="lb-1",
    algorithms="round_robin",      # or "least_connection"
    server_covered={"srv-1", "srv-2"},
)
```

**LB validation**

* `server_covered` must be a subset of declared servers.
* You must define **edges from the LB to each covered server** (see below).

### 3.4 Edges

```python
from asyncflow.components import Edge

edge = Edge(
    id="client-to-srv1",
    source="client-1",                      # may be external only for sources
    target="srv-1",                         # MUST be a declared node
    latency={"mean": 0.003, "distribution": "exponential"},
    # edge_type defaults to "network_connection"
    # dropout_rate defaults to 0.01 (0.0 .. 1.0)
)
```

**Semantics**

* `source`: can be an **external** ID for entry points (e.g., `"rqs-1"`).
* `target`: **must** be a declared node (`client`, `server`, `load_balancer`).
* `latency`: random variable; **`mean > 0`**, `variance ≥ 0` (if provided).
* **Fan-out rule**: the model enforces **“no fan-out except LB”**—i.e., only the load balancer may have multiple outgoing edges.

---

## 4) Global Settings: `SimulationSettings`

```python
from asyncflow.components import SimulationSettings

settings = SimulationSettings(
    total_simulation_time=600,  # seconds, default 3600, min 5
    sample_period_s=0.02,       # seconds, [0.001 .. 0.1], default 0.01
    enabled_sample_metrics=[
        "ready_queue_len",
        "event_loop_io_sleep",
        "ram_in_use",
        "edge_concurrent_connection",
    ],
    enabled_event_metrics=[
        "rqs_clock",
        # "llm_cost",  # optional future accounting
    ],
)
```

**Notes**

* Sampled metrics are time-series collected at `sample_period_s`.
* Event metrics are per-event (e.g., per request), not sampled.

---

## 5) Building the Payload with `AsyncFlow`

```python
from asyncflow import AsyncFlow
from asyncflow.schemas.payload import SimulationPayload  # optional typing

flow = (
    AsyncFlow()
    .add_generator(generator)
    .add_client(client)
    .add_servers(server)   # varargs
    .add_edges(*edges)     # varargs
    # .add_load_balancer(lb)
    .add_simulation_settings(settings)
)

payload: SimulationPayload = flow.build_payload()
```

**What `build_payload()` validates**

1. **Presence**: generator, client, ≥1 server, ≥1 edge, settings.
2. **Unique IDs**: servers and edges have unique IDs.
3. **Node types**: fixed enums: `client`, `server`, `load_balancer`.
4. **Edge integrity**: every target is a declared node; external IDs allowed only as sources; no self-loops.
5. **Load balancer sanity**: `server_covered ⊆ declared_servers` **and** there is an edge from the LB to **each** covered server.
6. **No fan-out except LB**: only the LB may have multiple outgoing edges.

If any rule is violated, a **descriptive `ValueError`** pinpoints the problem.

---

## 6) Running the Simulation

```python
import simpy
from asyncflow import SimulationRunner

env = simpy.Environment()
runner = SimulationRunner(env=env, simulation_input=payload)
results = runner.run()  # blocks until total_simulation_time

# Access results via the ResultsAnalyzer API:
stats = results.get_latency_stats()
ts, rps = results.get_throughput_series()
sampled = results.get_sampled_metrics()
```

You can also plot with the analyzer methods:

```python
from matplotlib import pyplot as plt  # optional
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
results.plot_latency_distribution(axes[0, 0])
results.plot_throughput(axes[0, 1])
results.plot_server_queues(axes[1, 0])
results.plot_ram_usage(axes[1, 1])
fig.tight_layout()
fig.savefig("single_server_builder.png")
```

---

## 7) Enums, Units & Conventions (Cheat Sheet)

* **Distributions**: `"poisson"`, `"normal"`, `"log_normal"`, `"exponential"`, `"uniform"`
* **Node types**: fixed internally to `generator`, `server`, `client`, `load_balancer`
* **Edge type**: `network_connection`
* **LB algorithms**: `"round_robin"`, `"least_connection"`
* **Step kinds**
  CPU: `"initial_parsing"`, `"cpu_bound_operation"`
  RAM: `"ram"`
  I/O: `"io_task_spawn"`, `"io_llm"`, `"io_wait"`, `"io_db"`, `"io_cache"`
* **Step operation keys**: `cpu_time`, `io_waiting_time`, `necessary_ram`
* **Sampled metrics**: `ready_queue_len`, `event_loop_io_sleep`, `ram_in_use`, `edge_concurrent_connection`
* **Event metrics**: `rqs_clock` (and `llm_cost` reserved for future use)

**Units & ranges**

* **Time**: seconds (`cpu_time`, `io_waiting_time`, latencies, `total_simulation_time`, `sample_period_s`, `user_sampling_window`)
* **RAM**: megabytes (`ram_mb`, `necessary_ram`)
* **Rates**: requests/minute (`avg_request_per_minute_per_user.mean`)
* **Probabilities**: `[0.0, 1.0]` (`dropout_rate`)
* **Bounds**: `total_simulation_time ≥ 5`, `sample_period_s ∈ [0.001, 0.1]`, `cpu_cores ≥ 1`, `ram_mb ≥ 256`, numeric step values > 0

