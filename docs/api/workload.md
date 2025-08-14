# AsyncFlow — Public Workload API

This page documents the **workload models** exported from:

```python
from asyncflow.workload import RqsGenerator, RVConfig
```

Use these to describe **how traffic is generated** (active users, per-user RPM, and the re-sampling window). The workload is independent from your topology and settings and plugs into the builder or payload directly.

> **Stability:** This is part of the public API. Fields and enum values are semver-stable (new options may be added in minor releases; breaking changes only in a major).

---

## Quick start

```python
from asyncflow.workload import RqsGenerator, RVConfig

rqs = RqsGenerator(
    id="rqs-1",
    avg_active_users=RVConfig(mean=100, distribution="poisson"),   # or "normal"
    avg_request_per_minute_per_user=RVConfig(mean=20, distribution="poisson"),
    user_sampling_window=60,  # seconds, re-sample active users every 60s
)

# … then compose with the builder
from asyncflow.builder.asyncflow_builder import AsyncFlow
payload = (AsyncFlow()
           .add_generator(rqs)
           # .add_client(...).add_servers(...).add_edges(...).add_simulation_settings(...)
           .build_payload())
```

---

## `RqsGenerator` (workload root)

```python
class RqsGenerator(BaseModel):
    id: str
    type: SystemNodes = SystemNodes.GENERATOR     # fixed
    avg_active_users: RVConfig                    # Poisson or Normal
    avg_request_per_minute_per_user: RVConfig    # Poisson (required)
    user_sampling_window: int = 60                # seconds, bounds [1, 120]
```

### Field reference

| Field                             | Type            | Allowed / Bounds                        | Description                                                                                                  |
| --------------------------------- | --------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `id`                              | `str`           | —                                       | Identifier used by edges (e.g., `source="rqs-1"`).                                                           |
| `type`                            | enum (fixed)    | `generator`                             | Constant; not user-set.                                                                                      |
| `avg_active_users`                | `RVConfig`      | **Distribution**: `poisson` or `normal` | Random variable for active concurrent users. If `normal`, variance is auto-filled (see `RVConfig`).          |
| `avg_request_per_minute_per_user` | `RVConfig`      | **Distribution**: **must be** `poisson` | Per-user rate (RPM). Enforced to Poisson by validator.                                                       |
| `user_sampling_window`            | `int` (seconds) | `1 ≤ value ≤ 120`                       | How often to re-sample `avg_active_users`. Larger windows → slower drift; smaller windows → more volatility. |

> Units: RPM = requests per **minute**; times are in **seconds**.

---

## `RVConfig` (random variables)

```python
class RVConfig(BaseModel):
    mean: float
    distribution: Distribution = "poisson"
    variance: float | None = None
```

### Behavior & validation

* **`mean`** is required and coerced to `float`. (Generic numeric check; positivity is **contextual**. For example, edge latency enforces `mean > 0`, while workloads accept `mean ≥ 0` and rely on samplers to truncate at 0 when needed.)
* **`distribution`** defaults to `"poisson"`.
* **Variance auto-fill:** if `distribution` is `"normal"` or `"log_normal"` **and** `variance` is omitted, it is set to `variance = mean`.

### Supported distributions

* `"poisson"`, `"normal"`, `"log_normal"`, `"exponential"`, `"uniform"`
  (For **workload**: `avg_active_users` → Poisson/Normal; `avg_request_per_minute_per_user` → **Poisson only**.)

---

## How the workload is sampled (engine semantics)

AsyncFlow provides **joint samplers** for the two main cases:

1. **Poisson–Poisson** (`avg_active_users ~ Poisson`, `rpm ~ Poisson`)

* Every `user_sampling_window` seconds, draw users:
  `U ~ Poisson(mean_users)`.
* Aggregate rate: `Λ = U * (rpm_per_user / 60)` (requests/second).
* Within the window, inter-arrival gaps are exponential:
  `Δt ~ Exponential(Λ)` (via inverse CDF).
* If `U == 0`, no arrivals until the next window.

2. **Gaussian–Poisson** (`avg_active_users ~ Normal`, `rpm ~ Poisson`)

* Draw users with **truncation at 0** (negative draws become 0):
  `U ~ max(N(mean, variance), 0)`.
* Then same steps as above: `Λ = U * (rpm_per_user / 60)`, `Δt ~ Exponential(Λ)`.

**Implications of `user_sampling_window`:**

* Smaller windows → more frequent changes in `U` (bursty arrivals).
* Larger windows → steadier rate within each window, fewer rate shifts.

---

## Examples

### A. Steady mid-load (Poisson–Poisson)

```python
rqs = RqsGenerator(
    id="steady",
    avg_active_users=RVConfig(mean=80, distribution="poisson"),
    avg_request_per_minute_per_user=RVConfig(mean=15, distribution="poisson"),
    user_sampling_window=60,
)
```

### B. Bursty users (Gaussian–Poisson)

```python
rqs = RqsGenerator(
    id="bursty",
    avg_active_users=RVConfig(mean=50, distribution="normal", variance=200),  # bigger var → burstier
    avg_request_per_minute_per_user=RVConfig(mean=18, distribution="poisson"),
    user_sampling_window=15,  # faster re-sampling → faster drift
)
```

### C. Tiny smoke test

```python
rqs = RqsGenerator(
    id="smoke",
    avg_active_users=RVConfig(mean=1, distribution="poisson"),
    avg_request_per_minute_per_user=RVConfig(mean=2, distribution="poisson"),
    user_sampling_window=30,
)
```

---

## YAML / JSON equivalence

If you configure via YAML/JSON, the equivalent block is:

```yaml
rqs_input:
  id: rqs-1
  avg_active_users:
    mean: 100
    distribution: poisson              # or normal
    # variance: 100                    # optional; auto=mean if normal/log_normal
  avg_request_per_minute_per_user:
    mean: 20
    distribution: poisson              # must be poisson
  user_sampling_window: 60             # [1..120] seconds
```

---

## Validation & error messages (what you can expect)

* `avg_request_per_minute_per_user.distribution != poisson`
  → `ValueError("At the moment the variable avg request must be Poisson")`
* `avg_active_users.distribution` not in `{poisson, normal}`
  → `ValueError("At the moment the variable active user must be Poisson or Gaussian")`
* Non-numeric `mean` in any `RVConfig`
  → `ValueError("mean must be a number (int or float)")`
* `user_sampling_window` outside `[1, 120]`
  → Pydantic range validation error with clear bounds in the message.

> Note: Positivity for means is enforced **contextually**. For workload, negative draws are handled by the samplers (e.g., truncated Normal). For edge latency, positivity is enforced at the edge model level.

---

## Common pitfalls & tips

* **Using Normal without variance:** If you set `distribution="normal"` and omit `variance`, it auto-fills to `variance=mean`. Set it explicitly if you want heavier or lighter variance than the default.
* **Confusing units:** RPM is **per minute**, not per second. The engine converts internally.
* **Over-reactive windows:** Very small `user_sampling_window` (e.g., `1–5s`) makes the rate jumpy; this is fine for “bursty” scenarios but can be noisy.
* **Zero arrivals:** If a window samples `U=0`, you’ll get no arrivals until the next window; this is expected.

---

## Interplay with Settings & Metrics

* The workload **does not** depend on the sampling cadence of time-series metrics (`SimulationSettings.sample_period_s`). Sampling controls **observability**, not arrivals.
* **Baseline sampled metrics are mandatory** in the current release (ready-queue length, I/O sleep, RAM, edge concurrency). Future metrics can be opt-in.

---

With `RqsGenerator` + `RVConfig` you can describe steady, bursty, or sparse loads with a few lines—then reuse the same topology and settings to compare how architecture choices behave under different traffic profiles.
