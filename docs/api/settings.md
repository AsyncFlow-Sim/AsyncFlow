
# AsyncFlow — Public API Reference: `settings`

This page documents the **public settings schema** you import from:

```python
from asyncflow.settings import SimulationSettings
```

These settings control **simulation duration**, **sampling cadence**, and **which metrics are collected**. The model is validated with Pydantic and ships with safe defaults.

> **Contract note**
> The four **baseline sampled metrics** are **mandatory** in the current release:
>
> * `ready_queue_len`
> * `event_loop_io_sleep`
> * `ram_in_use`
> * `edge_concurrent_connection`
>   Future metrics may be opt-in; these four must remain enabled.

---

## Imports

```python
from asyncflow.settings import SimulationSettings

# Optional: use enums instead of strings (recommended for IDE/type-checking)
from asyncflow.enums import SampledMetricName, EventMetricName
```

---

## Quick start

```python
from asyncflow.settings import SimulationSettings
from asyncflow.enums import SampledMetricName as S, EventMetricName as E

settings = SimulationSettings(
    total_simulation_time=300,   # seconds (≥ 5)
    sample_period_s=0.01,        # seconds, 0.001 ≤ value ≤ 0.1
    # Baseline sampled metrics are mandatory (may include more in future):
    enabled_sample_metrics={S.READY_QUEUE_LEN,
                            S.EVENT_LOOP_IO_SLEEP,
                            S.RAM_IN_USE,
                            S.EDGE_CONCURRENT_CONNECTION},
    # Event metrics (RQS_CLOCK is the default/mandatory one today):
    enabled_event_metrics={E.RQS_CLOCK},
)
```

Pass the object to the builder:

```python
from asyncflow import AsyncFlow

payload = (
    AsyncFlow()
    # … add workload, topology, edges …
    .add_simulation_settings(settings)
    .build_payload()
)
```

---

## Schema reference

### `SimulationSettings`

```python
SimulationSettings(
    total_simulation_time: int = 3600,  # ≥ 5
    sample_period_s: float = 0.01,      # 0.001 ≤ value ≤ 0.1
    enabled_sample_metrics: set[SampledMetricName] = {
        "ready_queue_len",
        "event_loop_io_sleep",
        "ram_in_use",
        "edge_concurrent_connection",
    },
    enabled_event_metrics: set[EventMetricName] = {"rqs_clock"},
)
```

**Fields**

* **`total_simulation_time`** *(int, default `3600`)*
  Simulation horizon in **seconds**. **Validation:** `≥ 5`.

* **`sample_period_s`** *(float, default `0.01`)*
  Sampling cadence for time-series metrics (seconds).
  **Validation:** `0.001 ≤ sample_period_s ≤ 0.1`.
  **Trade-off:** lower ⇒ higher temporal resolution but more samples/memory.

* **`enabled_sample_metrics`** *(set of enums/strings; default = baseline 4)*
  **Must include at least the baseline set** shown above. You can pass enum
  values or the corresponding strings.

* **`enabled_event_metrics`** *(set of enums/strings; default `{"rqs_clock"}`)*
  Per-event KPIs (not tied to `sample_period_s`). `rqs_clock` is required today;
  `llm_cost` is reserved for future use.

---

## Supported metric enums

You may pass **strings** or import the enums (recommended).

### Sampled (time-series)

* `ready_queue_len` — event-loop ready-queue length
* `event_loop_io_sleep` — time spent waiting on I/O in the loop
* `ram_in_use` — MB of RAM in use (per server)
* `edge_concurrent_connection` — concurrent connections per edge

```python
from asyncflow.enums import SampledMetricName as S
baseline = {S.READY_QUEUE_LEN, S.EVENT_LOOP_IO_SLEEP, S.RAM_IN_USE, S.EDGE_CONCURRENT_CONNECTION}
```

### Event (per-event)

* `rqs_clock` — start/end timestamps for each request (basis for latency)
* `llm_cost` — reserved for future cost accounting

```python
from asyncflow.enums import EventMetricName as E
SimulationSettings(enabled_event_metrics={E.RQS_CLOCK})
```

---

## Practical presets

* **Lean but compliant (fast inner-loop dev)**
  Keep baseline metrics; increase the sampling period to reduce cost:

  ```python
  SimulationSettings(
      total_simulation_time=10,
      sample_period_s=0.05,  # fewer samples
      # enabled_* use defaults with mandatory baseline & rqs_clock
  )
  ```

* **High-resolution debugging (short runs)**

  ```python
  SimulationSettings(
      total_simulation_time=60,
      sample_period_s=0.002,  # finer resolution
  )
  ```

* **Long scenarios (memory-friendly)**

  ```python
  SimulationSettings(
      total_simulation_time=1800,
      sample_period_s=0.05,   # fewer samples over long runs
  )
  ```

---

## YAML ⇄ Python mapping

| YAML (`sim_settings`)      | Python (`SimulationSettings`)  |
| -------------------------- | ------------------------------ |
| `total_simulation_time`    | `total_simulation_time`        |
| `sample_period_s`          | `sample_period_s`              |
| `enabled_sample_metrics[]` | `enabled_sample_metrics={...}` |
| `enabled_event_metrics[]`  | `enabled_event_metrics={...}`  |

Strings in YAML map to the same enum names used by Python.

---

## Validation & guarantees

* `total_simulation_time ≥ 5`
* `0.001 ≤ sample_period_s ≤ 0.1`
* `enabled_sample_metrics ⊇ {ready_queue_len, event_loop_io_sleep, ram_in_use, edge_concurrent_connection}`
* `enabled_event_metrics` must include `rqs_clock` (current contract)
* Enum names are part of the public contract (stable; new values may be added in minor versions)

---

## Tips & pitfalls

* **Memory/CPU budgeting**: total samples per metric ≈
  `total_simulation_time / sample_period_s`. Long runs with very small
  sampling periods produce large arrays.
* **Use enums for safety**: strings work, but enums enable IDE completion and mypy checks.
* **Forward compatibility**: additional sampled/event metrics may become available; the four baseline sampled metrics remain mandatory for the engine’s collectors.

---

This reflects your current implementation: baseline sampled metrics are **required**; event metrics currently require `rqs_clock`; and sampling bounds match the `SamplePeriods` constants.
