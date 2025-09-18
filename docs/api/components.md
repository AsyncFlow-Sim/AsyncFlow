# AsyncFlow — Public API Reference: `components`

This page documents the **public topology components** you can import from
`asyncflow.components` to construct a simulation scenario in Python.
These classes are Pydantic models with strict validation and are the
**only pieces you need** to define the *structure* of your system: nodes
(client/servers/LB), endpoints (steps), and network edges.

> The builder (`AsyncFlow`) will assemble these into the internal graph for you.
> You **do not** need to import internal graph classes.

---

## Imports

```python
from asyncflow.components import (
    Client,
    Server,
    ServerResources,
    LoadBalancer,
    Endpoint,
    Edge,
)
# Optional enums (strings are also accepted):
from asyncflow.enums import Distribution
```

---

## Quick example

```python
from asyncflow.components import (
    Client, Server, ServerResources, LoadBalancer, Endpoint, Edge
)

# Nodes
client = Client(id="client-1")

endpoint = Endpoint(
    endpoint_name="/predict",
    steps=[
        {"kind": "ram", "step_operation": {"necessary_ram": 64}},
        {"kind": "initial_parsing", "step_operation": {"cpu_time": 0.002}},
        {"kind": "io_wait", "step_operation": {"io_waiting_time": 0.010}},
    ],
)

server = Server(
    id="srv-1",
    server_resources=ServerResources(cpu_cores=2, ram_mb=2048),
    endpoints=[endpoint],
)

lb = LoadBalancer(id="lb-1", algorithms="round_robin", server_covered={"srv-1"})

# Edges (directed)
edges = [
    Edge(
        id="gen-to-client",
        source="rqs-1",        # external sources allowed (e.g., generator id)
        target="client-1",     # targets must be declared nodes
        latency={"mean": 0.003, "distribution": "exponential"},
    ),
    Edge(
        id="client-to-lb",
        source="client-1",
        target="lb-1",
        latency={"mean": 0.002, "distribution": "exponential"},
    ),
    Edge(
        id="lb-to-srv1",
        source="lb-1",
        target="srv-1",
        latency={"mean": 0.002, "distribution": "exponential"},
    ),
    Edge(
        id="srv1-to-client",
        source="srv-1",
        target="client-1",
        latency={"mean": 0.003, "distribution": "exponential"},
    ),
]
```

You can then feed these to the `AsyncFlow` builder (not shown here) along with
workload and settings.

---

## Component reference

### `Client`

```python
Client(id: str)
```

* Represents the client node.
* `type` is fixed internally to `"client"`.
* **Validation:** any non-standard `type` is rejected (guardrail).

---

### `ServerResources`

```python
ServerResources(
    cpu_cores: int = 1,          # ≥ 1 NOW MUST BE FIXED TO ONE
    ram_mb: int = 1024,          # ≥ 256
    db_connection_pool: int | None = None,
)
```

* Server capacity knobs used by the runtime (CPU tokens, RAM reservoir, optional DB pool).
* You may pass a **dict** instead of `ServerResources`; Pydantic will coerce it.

**Bounds & defaults**

* `cpu_cores ≥ 1`
* `ram_mb ≥ 256`
* `db_connection_pool` optional

---

### `Endpoint`

```python
Endpoint(
    endpoint_name: str,  # normalized to lowercase
    steps: list[dict],   # or Pydantic Step objects (dict is simpler)
)
```

Each step is a dict with **exactly one** operation:

```python
{"kind": <step-kind>, "step_operation": { <op-key>: <positive number> }}
```

**Valid step kinds and operation keys**

| Kind (enum string)    | Operation dict (exactly 1 key)   | Units / constraints |         |
| --------------------- | -------------------------------- | ------------------- | ------- |
| `initial_parsing`     | `{ "cpu_time": <float> }`        | seconds, > 0        |         |
| `cpu_bound_operation` | `{ "cpu_time": <float> }`        | seconds, > 0        |         |
| `ram`                 | \`{ "necessary\_ram": \<int      | float> }\`          | MB, > 0 |
| `io_task_spawn`       | `{ "io_waiting_time": <float> }` | seconds, > 0        |         |
| `io_llm`              | `{ "io_waiting_time": <float> }` | seconds, > 0        |         |
| `io_wait`             | `{ "io_waiting_time": <float> }` | seconds, > 0        |         |
| `io_db`               | `{ "io_waiting_time": <float> }` | seconds, > 0        |         |
| `io_cache`            | `{ "io_waiting_time": <float> }` | seconds, > 0        |         |

**Validation**

* `endpoint_name` is lowercased automatically.
* `step_operation` must have **one and only one** entry.
* The operation **must match** the step kind (CPU ↔ `cpu_time`, RAM ↔ `necessary_ram`, IO ↔ `io_waiting_time`).
* All numeric values must be **strictly positive**.

---

### `Server`

```python
Server(
    id: str,
    server_resources: ServerResources | dict,
    endpoints: list[Endpoint],
)
```

* Represents a server node hosting one or more endpoints.
* `type` is fixed internally to `"server"`.
* **Validation:** any non-standard `type` is rejected.

---

### `LoadBalancer` (optional)

```python
LoadBalancer(
    id: str,
    algorithms: Literal["round_robin", "least_connection"] = "round_robin",
    server_covered: set[str] = set(),
)
```

* Declares a logical load balancer and the set of server IDs it can route to.
* **Graph-level rules** (checked when the payload is built):

  * `server_covered` must be a subset of declared server IDs.
  * There must be an **edge from the LB to each covered server** (e.g., `lb-1 → srv-1`).

---

### `Edge`

```python
Edge(
    id: str,
    source: str,
    target: str,
    latency: dict | RVConfig,  # recommend dict: {"mean": <float>, "distribution": <enum>, "variance": <float?>}
    edge_type: Literal["network_connection"] = "network_connection",
    dropout_rate: float = 0.01,   # in [0.0, 1.0]
)
```

* Directed link between two nodes.
* **Latency** is a random variable; most users pass a dict:

  * `mean: float` (required)
  * `distribution: "poisson" | "normal" | "log_normal" | "exponential" | "uniform"` (default: `"poisson"`)
  * `variance: float?` (for `normal`/`log_normal`, defaults to `mean` if omitted)

**Validation**

* `mean > 0`
* if provided, `variance ≥ 0`
* `dropout_rate ∈ [0.0, 1.0]`
* `source != target`

**Graph-level rules** (enforced when the full payload is validated)

* Every **target** must be a **declared node** (`client`, `server`, or `load_balancer`).
* **External IDs** (e.g., `"rqs-1"`) are allowed **only** as **sources**; they cannot appear as targets.
* **Unique edge IDs**.
* **No fan-out except LB**: only the load balancer is allowed to have multiple outgoing edges among declared nodes.

---

## Type coercion & enums

* You may pass strings for enums (`kind`, `distribution`, etc.); they will be validated against the allowed values.
* For `ServerResources` and `Edge.latency` you can pass dictionaries; Pydantic will coerce them to typed models.
* If you prefer, you can import and use the enums:

  ```python
  from asyncflow.enums import Distribution
  Edge(..., latency={"mean": 0.003, "distribution": Distribution.EXPONENTIAL})
  ```

---

## Best practices & pitfalls

**Do**

* Keep IDs unique across nodes of the same category and across edges.
* Ensure LB coverage and LB→server edges are in sync.
* Use small, measurable step values first; iterate once you see where queues and delays form.

**Don’t**

* Create multiple outgoing edges from non-LB nodes (graph validator will fail).
* Use zero/negative times or RAM (validators will raise).
* Target external IDs (only sources may be external).

---

## Where these components fit

You will typically combine these **components** with:

* **workload** (`RqsGenerator`) from `asyncflow.workload`
* **settings** (`SimulationSettings`) from `asyncflow.settings`
* the **builder** (`AsyncFlow`) and **runner** (`SimulationRunner`) from the root package

Example (wiring, abbreviated):

```python
from asyncflow import AsyncFlow, SimulationRunner
from asyncflow.workload import RqsGenerator
from asyncflow.settings import SimulationSettings

flow = (
    AsyncFlow()
    .add_generator(RqsGenerator(...))
    .add_client(client)
    .add_servers(server)
    .add_edges(*edges)
    .add_load_balancer(lb)          # optional
    .add_simulation_settings(SimulationSettings(...))
)
payload = flow.build_payload()      # validates graph-level rules
SimulationRunner(..., simulation_input=payload).run()
```

---

With these `components`, you can model any topology supported by AsyncFlow—
cleanly, type-checked, and with **clear, early** validation errors when something
is inconsistent.
