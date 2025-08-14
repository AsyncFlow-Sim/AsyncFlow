# AsyncFlow — Public Enums API

This page documents the **public, user-facing** enums exported from `asyncflow.enums`. These enums exist to remove “magic strings” from scenario code, offer IDE autocomplete, and make input validation more robust. Using them is optional — all Pydantic models still accept the corresponding string values — but recommended for Python users.

```python
from asyncflow.enums import (
    Distribution,
    LbAlgorithmsName,
    SampledMetricName,
    EventMetricName,
    # advanced (optional, if you define steps in Python)
    EndpointStepCPU, EndpointStepIO, EndpointStepRAM, StepOperation,
)
```

> **Stability:** Values in these enums form part of the **public input contract**. They are semver-stable: new members may be added in minor releases, existing members won’t be renamed or removed except in a major release.

---

## 1) Distribution

Enumeration of probability distributions accepted by `RVConfig`.

* `Distribution.POISSON` → `"poisson"`
* `Distribution.NORMAL` → `"normal"`
* `Distribution.LOG_NORMAL` → `"log_normal"`
* `Distribution.EXPONENTIAL` → `"exponential"`
* `Distribution.UNIFORM` → `"uniform"`

**Used in:** `RVConfig` (e.g., workload users / rpm, edge latency).

**Notes & validation:**

* `mean` is required (coerced to float).
* For `NORMAL` and `LOG_NORMAL`, missing `variance` defaults to `mean`.
* For **edge latency** specifically, `mean > 0` and (if present) `variance ≥ 0`.

**Example**

```python
from asyncflow.enums import Distribution
from asyncflow.schemas.common.random_variables import RVConfig

rv = RVConfig(mean=0.003, distribution=Distribution.EXPONENTIAL)
```

---

## 2) LbAlgorithmsName

Load-balancing strategies available to the `LoadBalancer` node.

* `LbAlgorithmsName.ROUND_ROBIN` → `"round_robin"`
* `LbAlgorithmsName.LEAST_CONNECTIONS` → `"least_connection"`

**Used in:** `LoadBalancer(algorithms=...)`.

**Example**

```python
from asyncflow.enums import LbAlgorithmsName
from asyncflow.schemas.topology.nodes import LoadBalancer

lb = LoadBalancer(id="lb-1", algorithms=LbAlgorithmsName.ROUND_ROBIN, server_covered={"srv-1", "srv-2"})
```

---

## 3) SampledMetricName

Time-series metrics collected at a fixed cadence (`sample_period_s`).

* `READY_QUEUE_LEN` → `"ready_queue_len"`
* `EVENT_LOOP_IO_SLEEP` → `"event_loop_io_sleep"`
* `RAM_IN_USE` → `"ram_in_use"`
* `EDGE_CONCURRENT_CONNECTION` → `"edge_concurrent_connection"`

**Used in:** `SimulationSettings(enabled_sample_metrics=...)`.

**Example**

```python
from asyncflow.enums import SampledMetricName
from asyncflow.schemas.settings.simulation import SimulationSettings

settings = SimulationSettings(
    total_simulation_time=300,
    sample_period_s=0.01,
    enabled_sample_metrics={
        SampledMetricName.READY_QUEUE_LEN,
        SampledMetricName.RAM_IN_USE,
    },
)
```

---

## 4) EventMetricName

Per-event metrics (not sampled).

* `RQS_CLOCK` → `"rqs_clock"`
* `LLM_COST` → `"llm_cost"` (reserved for future accounting)

**Used in:** `SimulationSettings(enabled_event_metrics=...)`.

**Example**

```python
from asyncflow.enums import EventMetricName
SimulationSettings(enabled_event_metrics={EventMetricName.RQS_CLOCK})
```

---

## 5) (Advanced) Endpoint step enums

You only need these if you create `Endpoint` steps **programmatically** in Python. In YAML you’ll write strings; both modes are supported.

### 5.1 EndpointStepCPU

CPU-bound step kinds:

* `INITIAL_PARSING` → `"initial_parsing"`
* `CPU_BOUND_OPERATION` → `"cpu_bound_operation"`

### 5.2 EndpointStepRAM

RAM step kind:

* `RAM` → `"ram"`

### 5.3 EndpointStepIO

I/O-bound step kinds:

* `TASK_SPAWN` → `"io_task_spawn"`
* `LLM` → `"io_llm"`
* `WAIT` → `"io_wait"`
* `DB` → `"io_db"`
* `CACHE` → `"io_cache"`

### 5.4 StepOperation

Operation keys allowed inside `Step.step_operation`:

* `CPU_TIME` → `"cpu_time"` (seconds, positive)
* `NECESSARY_RAM` → `"necessary_ram"` (MB, positive)
* `IO_WAITING_TIME` → `"io_waiting_time"` (seconds, positive)

**Validation rules (enforced by the schema):**

* Every `Step` must have **exactly one** operation key.
* The operation must **match** the step kind:

  * CPU step → `CPU_TIME`
  * RAM step → `NECESSARY_RAM`
  * I/O step → `IO_WAITING_TIME`

**Example**

```python
from asyncflow.enums import EndpointStepCPU, EndpointStepIO, EndpointStepRAM, StepOperation
from asyncflow.schemas.topology.endpoint import Endpoint

ep = Endpoint(
    endpoint_name="/predict",
    steps=[
        { "kind": EndpointStepRAM.RAM, "step_operation": { StepOperation.NECESSARY_RAM: 128 } },
        { "kind": EndpointStepCPU.INITIAL_PARSING, "step_operation": { StepOperation.CPU_TIME: 0.002 } },
        { "kind": EndpointStepIO.DB, "step_operation": { StepOperation.IO_WAITING_TIME: 0.012 } },
    ],
)
```

---

## Usage patterns & tips

* **Strings vs Enums:** All models accept both. Enums help with IDE hints and prevent typos; strings keep YAML compact. Mix as you like.
* **Keep it public, not internal:** Only the enums above are considered public and stable. Internals like `SystemNodes`, `SystemEdges`, `ServerResourceName`, etc. are intentionally **not exported** (they may change).
* **Forward compatibility:** New enum members may appear in minor releases (e.g., a new `SampledMetricName`). Your existing configs remain valid; just opt in when you need them.

---

## Quick Reference

| Enum                | Where it’s used                             | Members (strings)                                                                                                        |
| ------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `Distribution`      | `RVConfig`                                  | `poisson`, `normal`, `log_normal`, `exponential`, `uniform`                                                              |
| `LbAlgorithmsName`  | `LoadBalancer.algorithms`                   | `round_robin`, `least_connection`                                                                                        |
| `SampledMetricName` | `SimulationSettings.enabled_sample_metrics` | `ready_queue_len`, `event_loop_io_sleep`, `ram_in_use`, `edge_concurrent_connection`                                     |
| `EventMetricName`   | `SimulationSettings.enabled_event_metrics`  | `rqs_clock`, `llm_cost`                                                                                                  |
| `EndpointStep*`     | `Endpoint.steps[*].kind` (Python)           | CPU: `initial_parsing`, `cpu_bound_operation`; RAM: `ram`; IO: `io_task_spawn`, `io_llm`, `io_wait`, `io_db`, `io_cache` |
| `StepOperation`     | `Endpoint.steps[*].step_operation`          | `cpu_time`, `necessary_ram`, `io_waiting_time`                                                                           |

---
