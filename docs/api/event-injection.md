# EventInjection — Public API Documentation

## Overview

`EventInjection` declares a **time-bounded event** that affects a component in the simulation. Each event targets either a **server** or a **network edge**, and is delimited by a `start` marker and an `end` marker.

Supported families (per code):

* **Server availability**: `SERVER_DOWN` → `SERVER_UP`
* **Network latency spike (deterministic offset in seconds)**: `NETWORK_SPIKE_START` → `NETWORK_SPIKE_END`
  For network spikes, the `Start` marker carries the amplitude in seconds via `spike_s`.

Strictness:

* Models use `ConfigDict(extra="forbid", frozen=True)`
  → unknown fields are rejected; instances are immutable at runtime.

---

## Data Model

### `Start`

* `kind: Literal[SERVER_DOWN, NETWORK_SPIKE_START]`
  Event family selector.
* `t_start: NonNegativeFloat`
  Start time in **seconds** from simulation start; **≥ 0.0**.
* `spike_s: PositiveFloat | None`
  **Required** and **> 0** **only** when `kind == NETWORK_SPIKE_START`.
  **Forbidden** (must be omitted/`None`) for any other kind.

### `End`

* `kind: Literal[SERVER_UP, NETWORK_SPIKE_END]`
  Must match the start family (see invariants).
* `t_end: PositiveFloat`
  End time in **seconds**; **> 0.0**.

### `EventInjection`

* `event_id: str`
  Unique identifier within the simulation payload.
* `target_id: str`
  Identifier of the affected component (server or edge) as defined in the topology.
* `start: Start`
  Start marker.
* `end: End`
  End marker.

---

## Validation & Invariants (as implemented)

### Within `EventInjection`

1. **Family coherence**

   * `SERVER_DOWN` → `SERVER_UP`
   * `NETWORK_SPIKE_START` → `NETWORK_SPIKE_END`
     Any other pairing raises:

   ```
   The event {event_id} must have as value of kind in end {expected}
   ```
2. **Temporal ordering**

   * `t_start < t_end` (with `t_start ≥ 0.0`, `t_end > 0.0`)
     Error:

   ```
   The starting time for the event {event_id} must be smaller than the ending time
   ```
3. **Network spike parameter**

   * If `start.kind == NETWORK_SPIKE_START` ⇒ `start.spike_s` **must** be provided and be a positive float (seconds).
     Error:

     ```
     The field spike_s for the event {event_id} must be defined as a positive float (seconds)
     ```
   * Otherwise (`SERVER_DOWN`) ⇒ `start.spike_s` **must be omitted** / `None`.
     Error:

     ```
     Event {event_id}: spike_s must be omitted for non-network events
     ```

### Enforced at `SimulationPayload` level

4. **Unique event IDs**
   Error:

   ```
   The id's representing different events must be unique
   ```
5. **Target existence & compatibility**

   * For server events (`SERVER_DOWN`), `target_id` must refer to a **server**.
   * For network spikes (`NETWORK_SPIKE_START`), `target_id` must refer to an **edge**.
     Errors:

   ```
   The target id {target_id} related to the event {event_id} does not exist
   ```

   ```
   The event {event_id} regarding a server does not have a compatible target id
   ```

   ```
   The event {event_id} regarding an edge does not have a compatible target id
   ```
6. **Times within simulation horizon** (with `T = sim_settings.total_simulation_time`)

   * `t_start >= 0.0` and `t_start <= T`
   * `t_end <= T`
     Errors:

   ```
   Event '{event_id}': start time t_start={t:.6f} must be >= 0.0
   Event '{event_id}': start time t_start={t:.6f} exceeds simulation horizon T={T:.6f}
   Event '{event_id}': end time t_end={t:.6f} exceeds simulation horizon T={T:.6f}
   ```
7. **Global liveness rule (servers)**
   The payload is rejected if **all servers are down at the same moment**.
   Implementation detail: the timeline is ordered so that, at identical timestamps, **`END` is processed before `START`** to avoid transient all-down states.
   Error:

   ```
   At time {time:.6f} all servers are down; keep at least one up
   ```

---

## Runtime Semantics (summary)

* **Server events**: the targeted server is unavailable between the start and end markers; the system enforces that at least one server remains up at all times.
* **Network spike events**: the targeted edge’s latency sampler is deterministically **shifted by `spike_s` seconds** during the event window (additive congestion model). The underlying distribution is not reshaped—samples are translated by a constant offset.

*(This reflects the agreed model: deterministic additive offset on edges.)*

---

## Units & Precision

* All times and offsets are in **seconds** (floating-point).
* Provide values with the precision your simulator supports; microsecond-level precision is acceptable if needed.

---

## Authoring Guidelines

* **Do not include `spike_s`** for non-network events.
* Use **stable, meaningful `event_id`** values for auditability.
* Keep events within the **simulation horizon**.
* When multiple markers share the same timestamp, rely on the engine’s **END-before-START** ordering for determinism.

---

## Examples

### 1) Valid — Server maintenance window

```yaml
event_id: ev-maint-001
target_id: srv-1
start: { kind: SERVER_DOWN, t_start: 120.0 }
end:   { kind: SERVER_UP,   t_end:   240.0 }
```

### 2) Valid — Network spike on an edge (+8 ms)

```yaml
event_id: ev-spike-008ms
target_id: edge-12
start: { kind: NETWORK_SPIKE_START, t_start: 10.0, spike_s: 0.008 }
end:   { kind: NETWORK_SPIKE_END,   t_end:   25.0 }
```

### 3) Invalid — Missing `spike_s` for a network spike

```yaml
event_id: ev-missing-spike
target_id: edge-5
start: { kind: NETWORK_SPIKE_START, t_start: 5.0 }
end:   { kind: NETWORK_SPIKE_END,   t_end:  15.0 }
```

Error:

```
The field spike_s for the event ev-missing-spike must be defined as a positive float (seconds)
```

### 4) Invalid — `spike_s` present for a server event

```yaml
event_id: ev-bad-spike
target_id: srv-2
start: { kind: SERVER_DOWN, t_start: 50.0, spike_s: 0.005 }
end:   { kind: SERVER_UP,   t_end:   60.0 }
```

Error:

```
Event ev-bad-spike: spike_s must be omitted for non-network events
```

### 5) Invalid — Mismatched families

```yaml
event_id: ev-bad-kinds
target_id: edge-1
start: { kind: NETWORK_SPIKE_START, t_start: 5.0, spike_s: 0.010 }
end:   { kind: SERVER_UP,           t_end:  15.0 }
```

Error:

```
The event ev-bad-kinds must have as value of kind in end NETWORK_SPIKE_END
```

### 6) Invalid — Start not before End

```yaml
event_id: ev-bad-time
target_id: srv-2
start: { kind: SERVER_DOWN, t_start: 300.0 }
end:   { kind: SERVER_UP,   t_end:   300.0 }
```

Error:

```
The starting time for the event ev-bad-time must be smaller than the ending time
```

---

## Notes for Consumers

* The schema is **strict**: misspelled fields (e.g., `t_strat`) are rejected.
* The engine may combine multiple active network spikes on the same edge by **summing** their `spike_s` values while they overlap (handled by runtime bookkeeping).
* This document describes exactly what is present in the provided code and validators; no additional fields or OpenAPI metadata are assumed.
