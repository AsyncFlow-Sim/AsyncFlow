### **FastSim — Simulation Input Schema**

The `SimulationPayload` is the single, self-contained contract that defines an entire simulation run. Its architecture is guided by a core philosophy: to achieve maximum control over input data through robust, upfront validation. To implement this, we extensively leverage Pydantic's powerful validation capabilities and Python's `Enum` classes. This approach creates a strictly-typed and self-consistent schema that guarantees any configuration is validated *before* the simulation engine starts.

This contract brings together three distinct but interconnected layers of configuration into one cohesive structure:

1.  **`rqs_input` (`RqsGeneratorInput`)**: Defines the **workload profile**—how many users are active and how frequently they generate requests.
2.  **`topology_graph` (`TopologyGraph`)**: Describes the **system's architecture**—its components, resources, and the network connections between them.
3.  **`settings` (`SimulationSettings`)**: Configures **global simulation parameters**, such as total runtime and which metrics to collect.

This layered design decouples the *what* (the system topology) from the *how* (the traffic pattern and simulation control), allowing for modular and reusable configurations. Adherence to our validation-first philosophy means every payload is rigorously parsed against this schema. By using a controlled vocabulary of `Enums` and the power of Pydantic, we guarantee that any malformed or logically inconsistent input is rejected upfront with clear, actionable errors, ensuring the simulation engine operates only on perfectly valid data.

---

### **1. Component: Traffic Profile (`RqsGeneratorInput`)**

This component specifies the dynamic behavior of users interacting with the system. It is built upon a foundation of shared constants and a reusable, rigorously validated random variable schema. This design ensures that any traffic profile is not only structurally correct but also logically sound before the simulation begins.

#### **Global Constants**

These enums provide a single source of truth for validation and default values, eliminating "magic strings" and ensuring consistency.

| Constant Set | Purpose | Key Values |
| :--- | :--- | :--- |
| **`TimeDefaults`** (`IntEnum`) | Defines default values and validation bounds for time-based fields. | `USER_SAMPLING_WINDOW = 60`, `MIN_USER_SAMPLING_WINDOW = 1`, `MAX_USER_SAMPLING_WINDOW = 120` |
| **`Distribution`** (`StrEnum`) | Defines the canonical names of supported probability distributions. | `"poisson"`, `"normal"`, `"log_normal"`, `"exponential"` |

---

#### **Random Variable Schema (`RVConfig`)**

At the core of the traffic generator is the `RVConfig`, a schema for defining stochastic variables. This allows critical parameters like user population and request rates to be modeled not as fixed numbers, but as draws from a probability distribution. Pydantic validators are used extensively to enforce correctness.

```python
class RVConfig(BaseModel):
    """class to configure random variables"""
    mean: float
    distribution: Distribution = Distribution.POISSON
    variance: float | None = None

    @field_validator("mean", mode="before")
    def ensure_mean_is_numeric(cls, v: object) -> float:
        # ... implementation ...

    @model_validator(mode="after")
    def default_variance(cls, model: "RVConfig") -> "RVConfig":
        # ... implementation ...
```

##### **Built-in Validation Logic**

Pydantic's validation system is leveraged to enforce several layers of correctness directly within the schema:

| Check | Pydantic Hook | Rule & Rationale |
| :--- | :--- | :--- |
| **Numeric `mean` Enforcement** | `@field_validator("mean", mode="before")` | This validator intercepts the `mean` field *before* any type casting. It ensures the provided value is an `int` or `float`, raising an explicit `ValueError` for invalid types like strings (`"100"`) or nulls. This prevents common configuration errors and guarantees a valid numeric type for all downstream logic. |
| **Valid `distribution` Name** | `Distribution` (`StrEnum`) type hint | By type-hinting the `distribution` field with the `Distribution` enum, Pydantic automatically ensures that its value must be one of the predefined members (e.g., `"poisson"`, `"normal"`). Any typo or unsupported value (like `"Poisson"` with a capital 'P') results in an immediate validation error. |
| **Intelligent `variance` Defaulting** | `@model_validator(mode="after")` | This powerful validator runs *after* all individual fields have been validated. It enforces a crucial business rule: if `distribution` is `"normal"` **and** `variance` is not provided, the schema automatically sets `variance = mean`. This provides a safe, logical default and simplifies configuration for the user, while ensuring the model is always self-consistent. |

---

#### **Payload Structure (`RqsGeneratorInput`)**

This is the main payload for configuring the traffic workload. It composes the `RVConfig` schema and adds its own validation rules.

| Field | Type | Validation & Purpose |
| :--- | :--- | :--- |
| `avg_active_users` | `RVConfig` | A random variable defining concurrent users. **Inherits all `RVConfig` validation**, ensuring its `mean`, `distribution`, and `variance` are valid. |
| `avg_request_per_minute_per_user` | `RVConfig` | A random variable for the user request rate. Also **inherits all `RVConfig` validation**. |
| `user_sampling_window` | `int` | The time duration (in seconds) for which the number of active users is held constant. Its value is **strictly bounded** by Pydantic's `Field` to be between `MIN_USER_SAMPLING_WINDOW` (1) and `MAX_USER_SAMPLING_WINDOW` (120). |

##### **How the Generator Uses Each Field**

The simulation evolves based on this robustly validated input:

1.  The timeline is divided into windows of `user_sampling_window` seconds. Because this value is range-checked upfront by Pydantic, the simulation is protected from invalid configurations like zero-length or excessively long windows.
2.  At the start of each window, a number of active users, `U(t)`, is drawn from the `avg_active_users` distribution. The embedded `RVConfig` guarantees this distribution is well-defined.
3.  Each of the `U(t)` users generates requests according to a rate drawn from `avg_request_per_minute_per_user`.

Because every numeric input is type-checked and range-checked by Pydantic before the simulation begins, **the runtime engine never needs to defend itself** against invalid data. This makes the core simulation loop leaner, more predictable, and free from redundant error-handling logic.

### **2. Component: System Blueprint (`TopologyGraph`)**

The topology schema is the static blueprint of the digital twin you wish to simulate. It describes the system's components, their resources, their behavior, and how they are interconnected. To ensure simulation integrity, FastSim uses this schema to rigorously validate the entire system description upfront, rejecting any inconsistencies before the simulation begins.

Of course. Here is the complete, consolidated, and highly detailed documentation for the `TopologyGraph` component, with all duplications removed and explanations expanded as requested.

---

### **2. Component: System Blueprint (`TopologyGraph`)**

The topology schema is the static blueprint of the digital twin you wish to simulate. It describes the system's components, their resources, their behavior, and how they are interconnected. To ensure simulation integrity, FastSim uses this schema to rigorously validate the entire system description upfront, rejecting any inconsistencies before the simulation begins.

#### **Design Philosophy: A "Micro-to-Macro" Approach**

The schema is built on a compositional, "micro-to-macro" principle. We start by defining the smallest indivisible units of work (`Step`) and progressively assemble them into larger, more complex structures (`Endpoint`, `Server`, and finally the `TopologyGraph`).

This layered approach provides several key advantages that enhance the convenience and reliability of crafting simulations:

*   **Modularity and Reusability:** Core operations are defined once as `Steps` and can be reused across multiple `Endpoints`. This modularity simplifies configuration, as complex workflows can be built from a library of simple, well-defined blocks.
*   **Local Reasoning, Global Safety:** Each model is responsible for its own internal consistency (e.g., a `Step` ensures its metric is valid for its kind). Parent models then enforce the integrity of the connections *between* these components (e.g., the `TopologyGraph` ensures all `Edges` connect to valid `Nodes`). This allows you to focus on one part of the configuration at a time, confident that the overall structure will be validated globally.
*   **Clarity and Maintainability:** The hierarchy is intuitive and mirrors how developers conceptualize system architecture. It is clear how atomic operations roll up into endpoints, which are hosted on servers connected by a network. This makes configuration files easy to read, write, and maintain over time.
*   **Guaranteed Robustness:** By catching all structural and referential errors before the simulation begins, this approach embodies the "fail-fast" principle. It guarantees that the SimPy engine operates on a valid, self-consistent model, eliminating a whole class of potential runtime bugs.

#### **A Controlled Vocabulary: Topology Constants**

The schema's robustness is founded on a controlled vocabulary defined by Python `Enum` classes. Instead of error-prone "magic strings" (e.g., `"cpu_operation"`), the schema uses these enums to define the finite set of legal values for categories like operation kinds, metrics, and node types. This design choice is critical for several reasons:

*   **Absolute Type-Safety:** Pydantic can validate input with certainty. Any value not explicitly defined in the corresponding `Enum` is immediately rejected, preventing subtle typos or incorrect values from causing difficult-to-debug runtime failures.
*   **Enhanced Developer Experience:** IDEs and static analysis tools like `mypy` can provide auto-completion and catch invalid values during development, offering immediate feedback long before the simulation is run.
*   **Single Source of Truth:** All valid categories are centralized. To add a new resource type or metric, a developer only needs to update the `Enum` definition, and the change propagates consistently throughout the validation logic.

| Constant Enum | Purpose |
| :--- | :--- |
| **`EndpointStepIO`, `EndpointStepCPU`, `EndpointStepRAM`** | Defines the exhaustive list of valid `kind` values for a `Step`. |
| **`Metrics`** | Specifies the legal dictionary keys within a `Step`'s `step_metrics`. |
| **`SystemNodes`** | Enumerate the allowed `type` for nodes (e.g., `"server"`, `"client"`). |
| **`SystemEdges`** | Enumerate the allowed categories for connections between nodes. |

---

### **Schema Hierarchy and In-Depth Validation**

Here we break down each component of the topology, highlighting the specific Pydantic validators that enforce its correctness and the deep rationale behind these choices.

#### **1. `Step`**: The Atomic Unit of Work
A `Step` represents a single, indivisible operation. Its validation is the cornerstone of ensuring that all work performed in the simulation is logical and well-defined.

| Validation Check | Pydantic Hook | Rule & Rationale |
| :--- | :--- | :--- |
| **Coherence of `kind` and `metric`** | `@model_validator` | **Rule:** The `step_metrics` dictionary must contain *exactly one* entry, and its key must be the correct metric for the `Step`'s `kind`. <br><br> **Rationale:** This is the most critical validation on a `Step`. The one-to-one mapping is a deliberate design choice for simplicity and robustness. It allows the simulation engine to be deterministic: a `cpu_bound_operation` step is routed to the CPU resource, an `io_wait` step to an I/O event, etc. This avoids the immense complexity of modeling operations that simultaneously contend for multiple resource types (e.g., CPU and RAM). This validator enforces that clear, unambiguous contract, preventing illogical pairings like a RAM allocation step being measured in `cpu_time`. |
| **Positive Metric Values** | `PositiveFloat` / `PositiveInt` | **Rule:** All numeric values in `step_metrics` must be greater than zero. <br><br> **Rationale:** It is physically impossible to spend negative or zero time on an operation or allocate negative RAM. This validation uses Pydantic's constrained types to offload this fundamental sanity check, ensuring that only plausible, positive resource requests enter the system and keeping the core simulation logic free of defensive checks against nonsensical data. |

#### **2. `Endpoint`**: Composing Workflows
An `Endpoint` defines a complete, user-facing operation (e.g., an API call like `/predict`) as an ordered sequence of `Steps`.

| Validation Check | Pydantic Hook | Rule & Rationale |
| :--- | :--- | :--- |
| **Consistent Naming** | `@field_validator("endpoint_name")` | **Rule:** Automatically converts the `endpoint_name` to lowercase. <br><br> **Rationale:** This enforces a canonical representation for all endpoint identifiers. It eliminates ambiguity and potential bugs that could arise from inconsistent capitalization (e.g., treating `/predict` and `/Predict` as different endpoints). This simple normalization makes the configuration more robust and simplifies endpoint lookups within the simulation engine. |

#### **3. System Nodes**: `Server` & `Client`
These models define the macro-components of your architecture where work is performed and resources are located.

| Validation Check | Pydantic Hook | Rule & Rationale |
| :--- | :--- | :--- |
| **Standardized Node `type`** | `@field_validator("type")` | **Rule:** The `type` field must strictly match the expected `SystemNodes` enum member (e.g., a `Server` object must have `type: "server"`). <br><br> **Rationale:** This provides a "belt-and-suspenders" check. Even if a default is provided, this validation prevents a user from explicitly overriding a node's type to a conflicting value. It enforces a strict contract: a `Server` object is always and only a server. This prevents object state confusion and simplifies pattern matching in the simulation engine. |
| **Unique Node IDs** | `@model_validator` in `TopologyNodes` | **Rule:** All `id` fields across all `Server` nodes and the `Client` node must be unique. <br><br> **Rationale:** This is fundamental to creating a valid graph. Node IDs are the primary keys used to address components. If two nodes shared the same ID, any `Edge` pointing to that ID would be ambiguous. This global validator prevents such ambiguity, guaranteeing that every node in the system is uniquely identifiable, which is a precondition for the final referential integrity check. |

#### **4. `Edge`**: Connecting the Components
An `Edge` represents a directed network link between two nodes, defining how requests flow through the system.

| Validation Check | Pydantic Hook | Rule & Rationale |
| :--- | :--- | :--- |
| **No Self-Loops** | `@model_validator` | **Rule:** An edge's `source` ID cannot be the same as its `target` ID. <br><br> **Rationale:** In the context of a distributed system topology, a network call from a service to itself is a logical anti-pattern. Such an operation would typically be modeled as an internal process (i.e., another `Step`), not a network hop. This validator prevents this common configuration error and simplifies the routing logic by disallowing trivial cycles. |

#### **5. `TopologyGraph`**: The Complete System
This is the root model that aggregates all `nodes` and `edges` and performs the final, most critical validation: ensuring referential integrity.

| Validation Check | Pydantic Hook | Rule & Rationale |
| :--- | :--- | :--- |
| **Referential Integrity** | `@model_validator` | **Rule:** Every `edge.source` and `edge.target` ID must correspond to an actual node ID defined in `TopologyNodes`. <br><br> **Rationale:** This is the capstone validation that guarantees the structural integrity of the entire system graph. It prevents "dangling edges"—connections that point to non-existent nodes. Without this check, the simulation could start with a broken topology and crash unexpectedly at runtime when a request attempts to traverse a broken link. By performing this check *after* all nodes and edges have been parsed, we ensure that the system described is a complete and validly connected graph, fully embodying the "fail-fast" principle. |

### **3. Component: Global Simulation Control (`SimulationSettings`)**

This final component configures the simulation's execution parameters and, critically, determines what data is collected. It acts as the master control panel for the simulation run, governing both its duration and the scope of its output.

#### **Payload Structure (`SimulationSettings`)**

```python
class SimulationSettings(BaseModel):
    """Global parameters that apply to the whole run."""
    total_simulation_time: int = Field(...)
    enabled_sample_metrics: set[SampledMetricName]
    enabled_event_metrics: set[EventMetricName]
```

| Field | Type | Purpose & Validation |
| :--- | :--- | :--- |
| `total_simulation_time` | `int` | The total simulation horizon in seconds. Must be `>= MIN_SIMULATION_TIME` (1800s). Defaults to `3600`. |
| `enabled_sample_metrics` | `set[SampledMetricName]` | A set of metrics to be sampled at fixed intervals, creating a time-series (e.g., `"ready_queue_len"`, `"ram_in_use"`). |
| `enabled_event_metrics` | `set[EventMetricName]` | A set of metrics recorded only when specific events occur, with no time-series (e.g., `"rqs_latency"`, `"llm_cost"`). |

---

#### **Design Rationale: Pre-validated, On-Demand Metrics for Robust and Efficient Collection**

The design of the `settings` component, particularly the `enabled_*_metrics` fields, is centered on two core principles: **user-driven selectivity** and **ironclad validation**. The rationale behind this approach is to create a system that is both flexible and fundamentally reliable.

##### **1. The Principle of User-Driven Selectivity**

We recognize that data collection is not free; it incurs performance overhead in terms of both memory (to store the data) and CPU cycles (to record it). Not every simulation requires every possible metric. For instance:
*   A simulation focused on CPU contention may not need detailed LLM cost tracking.
*   A high-level analysis of end-to-end latency might not require fine-grained data on event loop queue lengths.

By allowing the user to explicitly select only the metrics they need, we empower them to tailor the simulation to their specific analytical goals. This on-demand approach makes the simulator more efficient and versatile, avoiding the waste of collecting and processing irrelevant data.

##### **2. The Power of Ironclad, Upfront Validation**

This is where the design choice becomes critical for robustness. Simply allowing users to provide a list of strings is inherently risky due to potential typos or misunderstandings of metric names. Our schema mitigates this risk entirely through a strict, upfront validation contract.

*   **A Strict Contract via Enums:** The `enabled_sample_metrics` and `enabled_event_metrics` fields are not just sets of strings; they are sets of `SampledMetricName` and `EventMetricName` enum members. When Pydantic parses the input payload, it validates every single metric name provided by the user against these canonical `Enum` definitions.

*   **Immediate Rejection of Invalid Input:** If a user provides a metric name that is not a valid member of the corresponding enum (e.g., a typo like `"request_latncy"` or a misunderstanding like `"cpu_usage"` instead of `"core_busy"`), Pydantic immediately rejects the entire payload with a clear `ValidationError`. This happens *before* a single line of the simulation engine code is executed.

##### **3. The Benefit: Guaranteed Runtime Integrity**

This pre-validation provides a crucial and powerful guarantee to the simulation engine, leading to a safer and more efficient runtime:

*   **Safe, Error-Free Initialization:** At the very beginning of the simulation, the engine receives the *validated* set of metric names. It knows with absolute certainty the complete and exact set of metrics it needs to track. This allows it to safely initialize all necessary data collection structures (like dictionaries) at the start of the run. For example:
    ```python
    # This is safe because every key is guaranteed to be valid.
    event_results = {metric_name: [] for metric_name in settings.enabled_event_metrics}
    ```

*   **Elimination of Runtime KeyErrors:** Because all dictionary keys are guaranteed to exist from the start, the core data collection logic within the simulation's tight event loop becomes incredibly lean and robust. The engine never needs to perform defensive, conditional checks like `if metric_name in event_results: ...`. It can directly and safely access the key: `event_results[metric_name].append(value)`. This completely eliminates an entire class of potential `KeyError` exceptions, which are notoriously difficult to debug in complex, asynchronous simulations.

In summary, the design of `SimulationSettings` is a perfect example of the "fail-fast" philosophy. By forcing a clear and validated contract with the user upfront, we ensure that the data collection process is not only tailored and efficient but also fundamentally reliable. The engine operates with the confidence that the output data structures will perfectly and safely match the user's validated request, leading to a predictable and robust simulation from start to finish.
---

### **End-to-End Example (`SimulationPayload`)**

The following JSON object shows how these three components combine into a single, complete `SimulationPayload` for a minimal client-server setup.

```jsonc
{
  // Defines the traffic workload profile.
  "rqs_input": {
    "avg_active_users": {
      "mean": 50,
      "distribution": "poisson"
    },
    "avg_request_per_minute_per_user": {
      "mean": 5.0,
      "distribution": "normal",
      "variance": 1.0
    },
    "user_sampling_window": 60
  },
  // Describes the system's architectural blueprint.
  "topology_graph": {
    "nodes": {
      "client": {
        "id": "mobile_client",
        "type": "client"
      },
      "servers": [
        {
          "id": "api_server",
          "type": "server",
          "server_resources": {
            "cpu_cores": 4,
            "ram_mb": 4096
          },
          "endpoints": [
            {
              "endpoint_name": "/predict",
              "steps": [
                {
                  "kind": "initial_parsing",
                  "step_metrics": { "cpu_time": 0.005 }
                },
                {
                  "kind": "io_db",
                  "step_metrics": { "io_waiting_time": 0.050 }
                }
              ]
            }
          ]
        }
      ]
    },
    "edges": [
      {
        "source": "mobile_client",
        "target": "api_server",
        "latency": {
          "distribution": "log_normal",
          "mean": 0.04,
          "variance": 0.01
        }
      }
    ]
  },
  // Configures the simulation run and metric collection.
  "settings": {
    "total_simulation_time": 3600,
    "enabled_sample_metrics": [
      "ready_queue_len",
      "ram_in_use",
      "throughput_rps"
    ],
    "enabled_event_metrics": [
      "rqs_latency"
    ]
  }
}
```

### **Key Takeaways**

*   **Single Source of Truth**: `Enum` classes centralize all valid string literals, providing robust, type-safe validation across the entire schema.
*   **Layered Validation**: The `Constants → Component Schemas → SimulationPayload` hierarchy ensures that only well-formed and self-consistent configurations reach the simulation engine.
*   **Separation of Concerns**: The three top-level keys (`rqs_input`, `topology_graph`, `settings`) clearly separate the workload, the system architecture, and simulation control, making configurations easier to read, write, and reuse.




