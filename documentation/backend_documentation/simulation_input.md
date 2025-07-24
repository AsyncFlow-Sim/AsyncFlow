Of course. Here is the complete documentation, translated into English, based on the new Pydantic schemas.

-----

### **FastSim — Simulation Input Schema**

The `SimulationPayload` is the single, self-contained contract that defines an entire simulation run. Its architecture is guided by a core philosophy: to achieve maximum control over input data through robust, upfront validation. To implement this, we extensively leverage Pydantic's powerful validation capabilities and Python's `Enum` classes. This approach creates a strictly-typed and self-consistent schema that guarantees any configuration is validated *before* the simulation engine starts.

This contract brings together three distinct but interconnected layers of configuration into one cohesive structure:

1.  **`rqs_input` (`RqsGeneratorInput`)**: Defines the **workload profile**—how many users are active and how frequently they generate requests—and acts as the **source node** in our system graph.
2.  **`topology_graph` (`TopologyGraph`)**: Describes the **system's architecture**—its components, resources, and the network connections between them, represented as a directed graph.
3.  **`sim_settings` (`SimulationSettings`)**: Configures **global simulation parameters**, such as total runtime and which metrics to collect.

This layered design decouples the *what* (the system topology) from the *how* (the traffic pattern and simulation control), allowing for modular and reusable configurations. Adherence to our validation-first philosophy means every payload is rigorously parsed against this schema. By using a controlled vocabulary of `Enums` and the power of Pydantic, we guarantee that any malformed or logically inconsistent input is rejected upfront with clear, actionable errors, ensuring the simulation engine operates only on perfectly valid data.

-----

## **1. The System Graph (`topology_graph` and `rqs_input`)**

At the core of FastSim is the representation of the system as a **directed graph**. The **nodes** represent the architectural components (like servers, clients, and the traffic generator itself), while the **edges** represent the directed network connections between them. This graph-based approach allows for flexible and realistic modeling of request flows through distributed systems.

### **Design Philosophy: A "Micro-to-Macro" Approach**

The schema is built on a compositional, "micro-to-macro" principle. We start by defining the smallest indivisible units of work (`Step`) and progressively assemble them into larger, more complex structures (`Endpoint`, `Server`, and finally the `TopologyGraph`).

This layered approach provides several key advantages:

  * **Modularity and Reusability:** Core operations are defined once as `Steps` and can be reused across multiple `Endpoints`.
  * **Local Reasoning, Global Safety:** Each model is responsible for its own internal consistency (e.g., a `Step` ensures its metric is valid for its kind). Parent models then enforce the integrity of the connections *between* these components (e.g., the `TopologyGraph` ensures all `Edges` connect to valid `Nodes`).
  * **Guaranteed Robustness:** By catching all structural and referential errors before the simulation begins, this approach embodies the "fail-fast" principle. It guarantees that the SimPy engine operates on a valid, self-consistent model.

### **A Controlled Vocabulary: Topology Constants**

The schema's robustness is founded on a controlled vocabulary defined by Python `Enum` classes. Instead of error-prone "magic strings," the schema uses these enums to define the finite set of legal values for categories like operation kinds, metrics, and node types.

| Enum                       | Purpose                                                                   |
| :------------------------- | :------------------------------------------------------------------------ |
| **`EndpointStepCPU`, `EndpointStepRAM`, `EndpointStepIO`** | Defines the exhaustive list of valid `kind` values for a `Step`.          |
| **`StepOperation`** | Specifies the legal dictionary keys within a `Step`'s `step_operation`. |
| **`SystemNodes`** | Enumerate the allowed `type` for nodes (e.g., `"server"`, `"client"`, `"generator"`). |
| **`SystemEdges`** | Enumerate the allowed categories for connections between nodes.            |

-----

### **Schema Hierarchy and In-Depth Validation**

Here we break down each component of the topology, highlighting the specific Pydantic validators that enforce its correctness.

#### **Random Variable Schema (`RVConfig`)**

At the core of both the traffic generator and network latencies is `RVConfig`, a schema for defining stochastic variables. This allows critical parameters to be modeled not as fixed numbers, but as draws from a probability distribution.

| Check                         | Pydantic Hook                             | Rule & Rationale                                                                                                                                                                                                                                                        |
| :---------------------------- | :---------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Numeric `mean` Enforcement** | `@field_validator("mean", mode="before")` | Intercepts the `mean` field and ensures the provided value is an `int` or `float`, rejecting invalid types. This guarantees a valid numeric type for all downstream logic.                                                                                                |
| **Valid `distribution` Name** | `Distribution` (`StrEnum`) type hint      | Pydantic automatically ensures that the `distribution` field's value must be one of the predefined members (e.g., `"poisson"`, `"normal"`). Any typo or unsupported value results in an immediate validation error.                                                     |
| **Intelligent `variance` Defaulting** | `@model_validator(mode="after")`          | Enforces a crucial business rule: if `distribution` is `"normal"` or `"log_normal"` **and** `variance` is not provided, the schema automatically sets `variance = mean`. This provides a safe, logical default. |

#### **1. `Step`: The Atomic Unit of Work**

A `Step` represents a single, indivisible operation.

| Validation Check                 | Pydantic Hook          | Rule & Rationale                                                                                                                                                                                                                                                                                            |
| :------------------------------- | :--------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Coherence of `kind` and `step_operation`** | `@model_validator`     | **Rule:** The `step_operation` dictionary must contain *exactly one* entry, and its key (`StepOperation`) must be the correct metric for the `Step`'s `kind`. \<br\>\<br\> **Rationale:** This is the most critical validation on a `Step`. It prevents illogical pairings like a RAM allocation step being measured in `cpu_time`. It ensures every step has a clear, unambiguous impact on a single system resource. |
| **Positive Metric Values** | `PositiveFloat` / `PositiveInt` | **Rule:** All numeric values in `step_operation` must be greater than zero. \<br\>\<br\> **Rationale:** It is physically impossible to spend negative or zero time on an operation. This ensures that only plausible resource requests enter the system.                                                                     |

#### **2. `Endpoint`: Composing Workflows**

An `Endpoint` defines a complete operation (e.g., an API call like `/predict`) as an ordered sequence of `Steps`.

| Validation Check      | Pydantic Hook                      | Rule & Rationale                                                                                                                                                                          |
| :-------------------- | :--------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Consistent Naming** | `@field_validator("endpoint_name")` | **Rule:** Automatically converts the `endpoint_name` to lowercase. \<br\>\<br\> **Rationale:** This enforces a canonical representation, eliminating ambiguity from inconsistent capitalization (e.g., treating `/predict` and `/Predict` as the same). |

#### **3. System Nodes: `Server`, `Client`, and `RqsGeneratorInput`**

These models define the macro-components of your architecture where work is performed, resources are located, and requests originate.

| Validation Check                  | Pydantic Hook                             | Rule & Rationale                                                                                                                                                                                                                                                              |
| :-------------------------------- | :---------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Standardized Node `type`** | `@field_validator("type")`                | **Rule:** The `type` field must strictly match the expected `SystemNodes` enum member (e.g., a `Server` object must have `type: "server"`). \<br\>\<br\> **Rationale:** This enforces a strict contract: a `Server` object is always and only a server, preventing object state confusion.        |
| **Unique Node IDs** | `@model_validator` in `TopologyNodes`     | **Rule:** All `id` fields across all `Server` nodes, the `Client` node, and the `RqsGeneratorInput` node must be unique. \<br\>\<br\> **Rationale:** This is fundamental to creating a valid graph. Node IDs are the primary keys. If two nodes shared the same ID, any `Edge` pointing to that ID would be ambiguous. |
| **Workload Distribution Constraints** | `@field_validator` in `RqsGeneratorInput` | **Rule:** The `avg_request_per_minute_per_user` field must use a Poisson distribution. The `avg_active_users` field must use a Poisson or Normal distribution. \<br\>\<br\> **Rationale:** This is a current restriction of the simulation engine, which has a joint sampler optimized only for these combinations. This validator ensures that only supported configurations are accepted. |

#### **4. `Edge`: Connecting the Components**

An `Edge` represents a directed network link between two nodes.

| Validation Check  | Pydantic Hook      | Rule & Rationale                                                                                                                                                                                            |
| :---------------- | :----------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No Self-Loops** | `@model_validator` | **Rule:** An edge's `source` ID cannot be the same as its `target` ID. \<br\>\<br\> **Rationale:** A network call from a service to itself is a logical anti-pattern in a system topology. Such an operation should be modeled as an internal process (i.e., another `Step`), not a network hop. |
| **Unique Edge IDs** | `@model_validator` in `TopologyGraph` | **Rule:** All `id` fields of the `Edge`s must be unique. \<br\>\<br\> **Rationale:** Ensures that every network connection is uniquely identifiable, which is useful for logging and debugging. |

#### **5. `TopologyGraph`: The Complete System**

This is the root model that aggregates all `nodes` and `edges` and performs the final, most critical validation: ensuring referential integrity.

| Validation Check        | Pydantic Hook      | Rule & Rationale                                                                                                                                                                                                                                          |
| :---------------------- | :----------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Referential Integrity** | `@model_validator` | **Rule:** Every `edge.source` and `edge.target` ID must correspond to an actual node ID defined in the topology. \<br\>\<br\> **Rationale:** This is the capstone validation that guarantees the structural integrity of the entire system graph. It prevents "dangling edges"—connections that point to non-existent nodes—ensuring the described system is a complete and validly connected graph. |

-----

## **2. Global Simulation Control (`SimulationSettings`)**

This final component configures the simulation's execution parameters and, critically, determines what data is collected.

#### **Payload Structure (`SimulationSettings`)**

| Field                    | Type                       | Purpose & Validation                                                                                    |
| :----------------------- | :------------------------- | :------------------------------------------------------------------------------------------------------ |
| `total_simulation_time`  | `int`                      | The total simulation horizon in seconds. Must be `>=` a defined minimum (e.g., 1800s).                  |
| `enabled_sample_metrics` | `set[SampledMetricName]` | A set of metrics to be sampled at fixed intervals, creating a time-series (e.g., `"ready_queue_len"`, `"ram_in_use"`). |
| `enabled_event_metrics`  | `set[EventMetricName]`   | A set of metrics recorded only when specific events occur (e.g., `"rqs_latency"`).                      |

### **Design Rationale: Pre-validated, On-Demand Metrics**

The design of the `settings`, particularly the `enabled_*_metrics` fields, is centered on **user-driven selectivity** and **ironclad validation**.

1.  **Selectivity:** Data collection has a performance cost. By allowing the user to explicitly select only the metrics they need, we make the simulator more efficient and versatile.

2.  **Ironclad Validation:** Simply allowing users to provide a list of strings is risky. Our schema mitigates this risk by validating every metric name provided by the user against the canonical `Enum` definitions (`SampledMetricName`, `EventMetricName`). If a user provides a misspelled or invalid metric name (e.g., `"request_latncy"`), Pydantic immediately rejects the entire payload *before* the simulation engine runs.

This guarantees that the simulation engine can safely initialize all necessary data collection structures at the start of the run, completely eliminating an entire class of potential `KeyError` exceptions at runtime.

-----

## **End-to-End Example (`SimulationPayload`)**

The following JSON object shows how these components combine into a single `SimulationPayload` for a minimal client-server setup, updated according to the new schema.

```jsonc
{
  // Defines the workload profile as a generator node.
  "rqs_input": {
    "id": "mobile_user_generator",
    "type": "generator",
    "avg_active_users": {
      "mean": 50,
      "distribution": "poisson"
    },
    "avg_request_per_minute_per_user": {
      "mean": 5.0,
      "distribution": "poisson"
    },
    "user_sampling_window": 60
  },
  // Describes the system's architecture as a graph.
  "topology_graph": {
    "nodes": {
      "client": {
        "id": "entry_point_client",
        "type": "client"
      },
      "servers": [
        {
          "id": "api_server",
          "type": "server",
          "server_resources": {
            "cpu_cores": 4,
            "ram_mb": 4096,
            "db_connection_pool": 10
          },
          "endpoints": [
            {
              "endpoint_name": "/predict",
              "steps": [
                {
                  "kind": "initial_parsing",
                  "step_operation": { "cpu_time": 0.005 }
                },
                {
                  "kind": "io_db_query",
                  "step_operation": { "io_waiting_time": 0.050 }
                }
              ]
            }
          ]
        }
      ]
    },
    "edges": [
      {
        "id": "client_to_generator",
        "source": "entry_point_client",
        "target": "mobile_user_generator",
        "latency": {
          "distribution": "log_normal",
          "mean": 0.001,
          "variance": 0.0001
        }
      },
      {
        "id": "generator_to_api",
        "source": "mobile_user_generator",
        "target": "api_server",
        "latency": {
          "distribution": "log_normal",
          "mean": 0.04,
          "variance": 0.01
        },
        "probability": 1.0,
        "dropout_rate": 0.0
      }
    ]
  },
  // Configures the simulation run and metric collection.
  "sim_settings": {
    "total_simulation_time": 3600,
    "enabled_sample_metrics": [
      "ready_queue_len",
      "ram_in_use",
      "core_busy"
    ],
    "enabled_event_metrics": [
      "rqs_latency"
    ]
  }
}
```

### **Key Takeaways**

  * **Single Source of Truth**: `Enum` classes centralize all valid string literals, providing robust, type-safe validation across the entire schema.
  * **Layered Validation**: The `Constants → Component Schemas → SimulationPayload` hierarchy ensures that only well-formed and self-consistent configurations reach the simulation engine.
  * **Separation of Concerns**: The three top-level keys (`rqs_input`, `topology_graph`, `sim_settings`) clearly separate the workload, the system architecture, and simulation control, making configurations easier to read, write, and reuse.