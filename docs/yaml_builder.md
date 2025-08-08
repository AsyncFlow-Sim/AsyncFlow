# FastSim – YAML Input Guide

This guide explains **how to author the simulation YAML** for FastSim, covering every field, valid values, units, constraints, and the validation rules enforced by the Pydantic schemas.

The YAML you write is parsed into a single model:

```yaml
rqs_input:        # traffic generator (workload)
topology_graph:   # system architecture as a directed graph
sim_settings:     # global settings and metric collection config
```

Everything is **validated up front**. If something is inconsistent (e.g., an edge points to a non-existent node), the simulator raises a clear error before running.

---

## 1) Random Variables (`RVConfig`)

Many knobs use a **random variable** specification:

```yaml
mean: <float>                 # required
distribution: <enum>          # optional, default: poisson
variance: <float>             # optional; required by some distributions
```

### Supported distributions

* `poisson`
* `normal`
* `log_normal`
* `exponential`
* `uniform`

### Rules & defaults

* **`mean`** must be numeric (int or float). It is coerced to float.
* If `distribution` is `normal` or `log_normal` **and** `variance` is missing, it is set to `variance = mean`.
* For **edge latency** (see §3.3), additional checks apply: `mean > 0`, and if provided, `variance ≥ 0`.

**Units**

* Time values are **seconds**.
* Rates are **requests per minute** (where noted).

---

## 2) Workload: `rqs_input` (Request Generator)

```yaml
rqs_input:
  id: <string>
  # type is implicit and fixed to "generator"
  avg_active_users:
    mean: <float>
    distribution: poisson | normal       # ONLY these two are allowed
    variance: <float>                    # required if normal and not provided (auto=mean)
  avg_request_per_minute_per_user:
    mean: <float>
    distribution: poisson                # MUST be poisson
  user_sampling_window: <int seconds>    # default 60, bounds [1, 120]
```

### Semantics

* **`avg_active_users`**: expected concurrent users (a random variable).

  * Allowed distributions: **Poisson** or **Normal**.
* **`avg_request_per_minute_per_user`**: per-user request rate (RPM).

  * Must be **Poisson**.\*
* **`user_sampling_window`**: every N seconds the generator re-samples the active user count.

\* This reflects current sampler support (Poisson–Poisson and Gaussian–Poisson).

---

## 3) System Topology: `topology_graph`

The system is a **directed graph** of nodes and edges.

```yaml
topology_graph:
  nodes:
    client: { id: <string> }
    load_balancer:  # optional
      id: <string>
      algorithms: round_robin | least_connection
      server_covered: [ <server-id>, ... ]
    servers:
      - id: <string>
        server_resources:
          cpu_cores: <int≥1>
          ram_mb: <int≥256>
          db_connection_pool: <int|null>   # optional
        endpoints:
          - endpoint_name: <string>        # normalized to lowercase
            steps:
              - kind: <step-kind>          # see §3.2
                step_operation: { <op>: <value> }  # exactly ONE key (see §3.2)
  edges:
    - id: <string>
      source: <node-id or external-id>
      target: <node-id>                    # must be a declared node
      latency: { mean: <float>, distribution: <enum>, variance: <float?> }
      probability: <0..1>                  # default 1.0
      edge_type: network_connection        # (enum; current default/only)
      dropout_rate: <0..1>                 # default 0.01
```

### 3.1 Nodes

#### Client

```yaml
client:
  id: client-1
  # type is fixed to "client"
```

#### Server

```yaml
- id: srv-1
  # type is fixed to "server"
  server_resources:
    cpu_cores: 1                 # default 1, min 1
    ram_mb: 1024                 # default 1024, min 256
    db_connection_pool: null     # optional; set an integer to enable pool modeling
  endpoints:
    - endpoint_name: /predict
      steps:
        # defined in §3.2
```

**Resource semantics**

* `cpu_cores`: number of worker “core tokens” available for CPU-bound step execution.
* `ram_mb`: total available RAM (MB) tracked as a reservoir; steps reserve then release.
* `db_connection_pool`: optional capacity bound for DB-like steps (future-use; declared here for forward compatibility).

#### Load Balancer (optional)

```yaml
load_balancer:
  id: lb-1
  algorithms: round_robin | least_connection
  server_covered: [ srv-1, srv-2 ]  # must be a subset of declared server IDs
```

LB **validation**:

* `server_covered` must be a subset of declared servers.
* You must also define **edges from the LB to each covered server** (see §3.3); otherwise validation fails.

### 3.2 Endpoints & Steps

An endpoint is a **linear sequence** of steps.
Each step must declare **exactly one** operation (`step_operation`) whose key matches the step’s kind.

#### Step kinds (enums)

**CPU-bound**

* `initial_parsing`
* `cpu_bound_operation`

**RAM**

* `ram`

**I/O-bound** (all use `io_waiting_time` as the operation key)

* `io_task_spawn`    (spawns a background task, returns immediately)
* `io_llm`           (LLM inference call)
* `io_wait`          (generic wait, non-blocking)
* `io_db`            (DB roundtrip)
* `io_cache`         (cache access)

#### Operation keys (enum `StepOperation`)

* `cpu_time`: service time (seconds) that **occupies a CPU core/GIL**.
* `necessary_ram`: peak RAM (MB) reserved for the step.
* `io_waiting_time`: passive wait (seconds) **without a CPU core**.

#### Valid pairings

* CPU step → `{ cpu_time: <PositiveFloat> }`
* RAM step → `{ necessary_ram: <PositiveInt|PositiveFloat> }`
* I/O step → `{ io_waiting_time: <PositiveFloat> }`

**Example**

```yaml
endpoints:
  - endpoint_name: /hello
    steps:
      - kind: ram
        step_operation: { necessary_ram: 64 }
      - kind: initial_parsing
        step_operation: { cpu_time: 0.002 }
      - kind: io_cache
        step_operation: { io_waiting_time: 0.003 }
      - kind: io_db
        step_operation: { io_waiting_time: 0.012 }
      - kind: cpu_bound_operation
        step_operation: { cpu_time: 0.001 }
```

**Validation enforced**

* `step_operation` must contain **exactly one** entry.
* The operation key must match the step kind (e.g., RAM cannot use `cpu_time`).
* All numeric values are **strictly positive**.

### 3.3 Edges

```yaml
- id: c2s
  source: client-1           # may be an external ID only for sources
  target: srv-1              # MUST be a declared node
  latency:
    mean: 0.003
    distribution: exponential
    # variance optional; if normal/log_normal and missing → set to mean
  probability: 1.0           # optional [0..1]
  edge_type: network_connection
  dropout_rate: 0.01         # optional [0..1]
```

**Semantics**

* **`source`** can be an external entry point (e.g., `rqs-1`) for inbound edges.
* **`target`** must always reference a declared node: client, server, or LB.
* **`latency`** is a random variable; **`mean > 0`**, **`variance ≥ 0`** (if provided).
* **`probability`** is used when multiple outgoing edges exist from a node.
* **`dropout_rate`** models probabilistic packet/request loss on the link.

---

## 4) Global Settings: `sim_settings`

```yaml
sim_settings:
  total_simulation_time: <int seconds>   # default 3600, min 5
  sample_period_s: <float seconds>       # default 0.01, bounds [0.001, 0.1]
  enabled_sample_metrics:
    - ready_queue_len
    - event_loop_io_sleep
    - ram_in_use
    - edge_concurrent_connection
  enabled_event_metrics:
    - rqs_clock
    # - llm_cost   # optional, for future accounting
```

**Notes**

* `enabled_sample_metrics` are **time-series** collected every `sample_period_s`.
* `enabled_event_metrics` are **per-event** (e.g., per request) and not tied to the sampling period.
* The defaults already include the four main sampled metrics and `rqs_clock`.

---

## 5) Graph-level Validation Rules (what’s checked before running)

FastSim validates the entire payload. Key checks include:

1. **Unique IDs**

   * All server IDs are unique.
   * Edge IDs are unique.
2. **Node Types**

   * `type` fields on nodes are fixed to: `client`, `server`, `load_balancer`.
3. **Edge referential integrity**

   * Every **target** is a declared node ID.
   * **External IDs** are allowed **only** as **sources**. If an ID appears as an external source, it must **never** appear as a target anywhere.
4. **No self-loops**

   * `source != target` for every edge.
5. **Load balancer sanity**

   * `server_covered` is a subset of declared servers.
   * There is an **edge from the LB to every covered server**.

If any rule is violated, the simulator raises a descriptive error.

---

## 6) End-to-End Examples

### 6.1 Minimal single-server scenario

```yaml
rqs_input:
  id: rqs-1
  avg_active_users: { mean: 50, distribution: poisson }
  avg_request_per_minute_per_user: { mean: 30, distribution: poisson }
  user_sampling_window: 60

topology_graph:
  nodes:
    client: { id: client-1 }
    servers:
      - id: srv-1
        server_resources: { cpu_cores: 1, ram_mb: 1024 }
        endpoints:
          - endpoint_name: /hello
            steps:
              - kind: ram
                step_operation: { necessary_ram: 32 }
              - kind: initial_parsing
                step_operation: { cpu_time: 0.002 }
              - kind: io_wait
                step_operation: { io_waiting_time: 0.010 }
  edges:
    - id: gen-to-client
      source: rqs-1
      target: client-1
      latency: { mean: 0.003, distribution: exponential }
    - id: client-to-server
      source: client-1
      target: srv-1
      latency: { mean: 0.003, distribution: exponential }
    - id: server-to-client
      source: srv-1
      target: client-1
      latency: { mean: 0.003, distribution: exponential }

sim_settings:
  total_simulation_time: 300
  sample_period_s: 0.01
  enabled_sample_metrics:
    - ready_queue_len
    - event_loop_io_sleep
    - ram_in_use
    - edge_concurrent_connection
  enabled_event_metrics:
    - rqs_clock
```

### 6.2 With a load balancer and two servers

```yaml
rqs_input:
  id: rqs-1
  avg_active_users: { mean: 120, distribution: poisson }
  avg_request_per_minute_per_user: { mean: 20, distribution: poisson }

topology_graph:
  nodes:
    client: { id: client-1 }
    load_balancer:
      id: lb-1
      algorithms: round_robin
      server_covered: [ srv-1, srv-2 ]
    servers:
      - id: srv-1
        server_resources: { cpu_cores: 1, ram_mb: 1024 }
        endpoints:
          - endpoint_name: /api
            steps:
              - kind: ram
                step_operation: { necessary_ram: 64 }
              - kind: cpu_bound_operation
                step_operation: { cpu_time: 0.004 }
      - id: srv-2
        server_resources: { cpu_cores: 2, ram_mb: 2048 }
        endpoints:
          - endpoint_name: /api
            steps:
              - kind: ram
                step_operation: { necessary_ram: 64 }
              - kind: io_db
                step_operation: { io_waiting_time: 0.012 }

  edges:
    - { id: gen-client,   source: rqs-1,    target: client-1,
        latency: { mean: 0.003, distribution: exponential } }

    - { id: client-lb,    source: client-1, target: lb-1,
        latency: { mean: 0.002, distribution: exponential } }

    - { id: lb-srv1,      source: lb-1,     target: srv-1,
        latency: { mean: 0.002, distribution: exponential }, probability: 0.5 }
    - { id: lb-srv2,      source: lb-1,     target: srv-2,
        latency: { mean: 0.002, distribution: exponential }, probability: 0.5 }

    - { id: srv1-client,  source: srv-1,    target: client-1,
        latency: { mean: 0.003, distribution: exponential } }
    - { id: srv2-client,  source: srv-2,    target: client-1,
        latency: { mean: 0.003, distribution: exponential } }

sim_settings:
  total_simulation_time: 600
  sample_period_s: 0.02
  enabled_sample_metrics: [ ready_queue_len, ram_in_use, edge_concurrent_connection ]
  enabled_event_metrics: [ rqs_clock ]
```

## 7) Common Pitfalls & How to Avoid Them

* **Mismatched step operations**
  A CPU step must use `cpu_time`; an I/O step must use `io_waiting_time`; a RAM step must use `necessary_ram`. The validator enforces **exactly one** key.

* **Edge targets must be declared nodes**
  `source` can be external (e.g., `rqs-1`), but **no external ID** may ever appear as a **target**.

* **Load balancer coverage without edges**
  If the LB declares `server_covered: [srv-1, srv-2]`, you must also add edges `lb→srv-1` and `lb→srv-2`.

* **Latency RV rules on edges**
  For edge latency, `mean` must be **> 0**; if `variance` is present, it must be **≥ 0**.

* **Sampling too coarse**
  If `sample_period_s` is large, short spikes in queues may be missed. Lower it (e.g., `0.005`) to capture fine-grained bursts—at the cost of larger time-series.

---

## 8) Quick Reference (Enums)

* **Distributions**: `poisson`, `normal`, `log_normal`, `exponential`, `uniform`
* **Node types**: `generator`, `server`, `client`, `load_balancer` (fixed by model)
* **Edge types**: `network_connection`
* **LB algorithms**: `round_robin`, `least_connection`
* **Step kinds**
  CPU: `initial_parsing`, `cpu_bound_operation`
  RAM: `ram`
  I/O: `io_task_spawn`, `io_llm`, `io_wait`, `io_db`, `io_cache`
* **Step operation keys**: `cpu_time`, `io_waiting_time`, `necessary_ram`
* **Sampled metrics**: `ready_queue_len`, `event_loop_io_sleep`, `ram_in_use`, `edge_concurrent_connection`
* **Event metrics**: `rqs_clock` (and `llm_cost` reserved for future use)

---

## 9) Units & Conventions

* **Time**: seconds (`cpu_time`, `io_waiting_time`, latencies, `total_simulation_time`, `sample_period_s`, `user_sampling_window`)
* **RAM**: megabytes (`ram_mb`, `necessary_ram`)
* **Rates**: requests/minute (`avg_request_per_minute_per_user.mean`)
* **Probabilities**: `[0.0, 1.0]` (`probability`, `dropout_rate`)
* **IDs**: strings; must be **unique** per category (servers, edges, LB).

---

If you stick to these rules and examples, your YAML will parse cleanly and the simulation will run with a self-consistent, strongly-validated model.
