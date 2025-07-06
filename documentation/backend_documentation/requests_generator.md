# Requests Generator

This document describes the design of the **requests generator**, which models a stream of user requests to a given endpoint over time.

---

## Model Inputs and Output

Following the FastSim philosophy, we accept a small set of input parameters to drive a “what-if” analysis in a pre-production environment. These inputs let you explore reliability and cost implications under different traffic scenarios.

**Inputs**

1. **Average concurrent users** – expected number of users (or sessions) simultaneously hitting the endpoint.
2. **Average requests per minute per user** – average number of requests each user issues per minute.
3. **Simulation time** – total duration of the simulation, in seconds.

**Output**
A continuous sequence of timestamps (seconds) marking individual request arrivals.

---

## Model Assumptions

* *Concurrent users* and *requests per minute per user* are **random variables**.
* *Simulation time* is **deterministic**.

We model:

* **Requests per minute per user** as Poisson($\lambda_r$).
* **Concurrent users** as either Poisson($\lambda_u$) or truncated Normal.

```python
from pydantic import BaseModel
from typing  import Literal

class RVConfig(BaseModel):
    """Configure a random-variable parameter."""
    mean: float
    distribution: Literal["poisson", "normal", "gaussian"] = "poisson"
    variance: float | None = None  # required only for normal/gaussian

class SimulationInput(BaseModel):
    """Define simulation inputs."""
    avg_active_users: RVConfig
    avg_request_per_minute_per_user: RVConfig
    total_simulation_time: int | None = None
```

---

## Aggregate Request Rate

From the two random inputs we define the **per-second aggregate rate** $\Lambda$:

$$
\Lambda
  = \text{concurrent\_users}
  \;\times\;
  \frac{\text{requests\_per\_minute\_per\_user}}{60}
  \quad[\text{requests/s}].
$$

---

## 1. Poisson → Exponential Refresher

### 1.1 Homogeneous Poisson process

A Poisson process of rate $\lambda$ has

$$
\Pr\{N(t)=k\}
  = e^{-\lambda t}\,\frac{(\lambda t)^{k}}{k!},\quad k=0,1,2,\dots
$$

### 1.2 Waiting time to first event

Define $T_1=\inf\{t>0:N(t)=1\}$.
The survival function is

$$
\Pr\{T_1>t\}
  = \Pr\{N(t)=0\}
  = e^{-\lambda t},
$$

so the CDF is

$$
F_{T_1}(t) = 1 - e^{-\lambda t},\quad t\ge0,
$$

and the density $f(t)=\lambda\,e^{-\lambda t}$.  Thus

$$
T_1 \sim \mathrm{Exp}(\lambda),
$$

and by memorylessness every inter-arrival gap $\Delta t_i$ is i.i.d. Exp($\lambda$).

### 1.3 Inverse-CDF sampling

To draw $\Delta t\sim\mathrm{Exp}(\lambda)$:

1. Sample $U\sim\mathcal U(0,1)$.
2. Solve $U=1-e^{-\lambda\,\Delta t}$;$\Rightarrow\;\Delta t=-\ln(1-U)/\lambda$.
3. Equivalent compact form:
   $\displaystyle \Delta t = -\,\ln(U)/\lambda$.

---

## 2. Poisson × Poisson Workload

### 2.1 Notation

| Symbol                            | Meaning                                 | Law      |
| --------------------------------- | --------------------------------------- | -------- |
| $U\sim\mathrm{Pois}(\lambda_u)$   | active users in current 1-minute window | Poisson  |
| $R_i\sim\mathrm{Pois}(\lambda_r)$ | requests per minute by user *i*         | Poisson  |
| $N=\sum_{i=1}^U R_i$              | total requests in that minute           | compound |
| $\Lambda=N/60$                    | aggregate rate (requests / second)      | compound |

All $R_i$ are independent of each other and of $U$.

### 2.2 Conditional sum ⇒ Poisson

Given $U=u$:

$$
N\mid U=u
=\sum_{i=1}^{u}R_i
\;\sim\;\mathrm{Pois}(u\,\lambda_r).
$$

### 2.3 Unconditional law of $N$

By the law of total probability:

$$
\Pr\{N=n\}
=\sum_{u=0}^{\infty}
\Pr\{U=u\}\;
\Pr\{N=n\mid U=u\}
\;=\;
e^{-\lambda_u}\,\frac1{n!}
\sum_{u=0}^{\infty}
\frac{\lambda_u^u}{u!}\,
e^{-u\lambda_r}\,(u\lambda_r)^n.
$$

This is the **Poisson–Poisson compound** (Borel–Tanner) distribution.

---

## 3. Exact Hierarchical Sampler

Rather than invert the discrete CDF above, we exploit the conditional structure:

```python
# Hierarchical sampler code snippet
now = 0.0                 # virtual clock (s)
window_end = 0.0          # end of the current user window
Lambda = 0.0              # aggregate rate Λ (req/s)

while now < simulation_time:
    # (Re)sample U at the start of each window
    if now >= window_end:
        window_end = now + float(sampling_window_s)
        users = poisson_variable_generator(mean_concurrent_user, rng)
        Lambda = users * mean_req_per_sec_per_user

    # No users → fast-forward to next window
    if Lambda <= 0.0:
        now = window_end
        continue

    # Exponential gap from a protected uniform value
    u_raw = max(uniform_variable_generator(rng), 1e-15)
    delta_t = -math.log(1.0 - u_raw) / Lambda

    # End simulation if the next event exceeds the horizon
    if now + delta_t > simulation_time:
        break

    # If the gap crosses the window boundary, jump to it
    if now + delta_t >= window_end:
        now = window_end
        continue

    now += delta_t
    yield delta_t
```

Because each conditional step matches the exact Poisson→Exponential law, this two-stage algorithm reproduces the same joint distribution as analytically inverting the compound CDF, but with minimal computation.

---

## 4. Validity of the hierarchical sampler

The validity of the hierarchical sampler relies on a structural property of the model:

$$
N \;=\; \sum_{i=1}^{U} R_i,
$$

where each $R_i \sim \mathrm{Pois}(\lambda_r)$ is independent of the others and of $U$.  Because the Poisson family is closed under convolution,

$$
N \,\big|\, U=u \;\sim\; \mathrm{Pois}\!\bigl(u\,\lambda_r\bigr).
$$

This result has two important consequences:

1. **Deterministic conditional rate** – Given $U=u$, the aggregate request arrivals constitute a homogeneous Poisson process with the *deterministic* rate

   $$
     \Lambda = \frac{u\,\lambda_r}{60}.
   $$

   All inter-arrival gaps are therefore i.i.d. exponential with parameter $\Lambda$, allowing us to use the standard inverse–CDF formula for each gap.

2. **Layered uncertainty handling** – The randomness associated with $U$ is handled in an outer step (sampling $U$ once per window), while the inner step leverages the well-known Poisson→Exponential correspondence.  This two-level construction reproduces exactly the joint distribution obtained by first drawing $\Lambda = N/60$ from the compound Poisson law and then drawing gaps conditional on $\Lambda$.

If the total count could **not** be written as a sum of independent Poisson variables, the conditional distribution of $N$ would no longer be Poisson and the exponential-gap shortcut would not apply.  In that situation one would need to work directly with the (generally more complex) mixed distribution of $\Lambda$ or adopt another specialized sampling scheme.



## 5. Equivalence to CDF Inversion

By the law of total probability, for any event set $A$:

$$
\Pr\{(\Lambda,\Delta t_1,\dots)\in A\}
=\sum_{u=0}^\infty
\Pr\{U=u\}\;
\Pr\{(\Lambda,\Delta t_1,\dots)\in A\mid U=u\}.
$$

Step 1 samples $\Pr\{U=u\}$, step 2–3 sample the conditional exponential gaps. Because these two factors exactly match the mixture definition of the compound CDF, the hierarchical sampler **is** an exact implementation of two-stage CDF inversion, avoiding any explicit inversion of an infinite series.

---

## 6. Gaussian × Poisson Variant

If concurrent users follow a truncated Normal,

$$
U\sim \max\{0,\;\mathcal N(\mu_u,\sigma_u^2)\},
$$

steps 2–3 remain unchanged; only step 1 draws $U$ from a continuous law. The resulting mixture is continuous, yet the hierarchical sampler remains exact.

---

## 7. Time Window

The sampling window length governs how often we re-sample $U$. It should reflect the timescale over which user count fluctuations become significant. Our default is **60 s**, but you can adjust this parameter in your configuration before each simulation.

---

## Limitations of the Requests Model

1. **Independence assumption**
   Assumes per-user streams and $U$ are independent. Real traffic often exhibits user-behavior correlations (e.g., flash crowds).

2. **Exponential inter-arrival times**
   Implies memorylessness; cannot capture self-throttling or long-range dependence found in real workloads.

3. **No diurnal/trend component**
   User count $U$ is IID per window. To model seasonality or trends, you must vary $\lambda_u(t)$ externally.

4. **No burst-control or rate-limiting**
   Does not simulate client-side throttling or server back-pressure. Any rate-limit logic must be added externally.

5. **Gaussian truncation artifacts**
   In the Gaussian–Poisson variant, truncating negatives to zero and rounding can under-estimate extreme user counts.


**Key takeaway:** By structuring the generator as
$\Lambda = U\,\lambda_r/60$ with a two-stage Poisson→Exponential sampler, FastSim efficiently reproduces compound Poisson traffic dynamics without any complex CDF inversion.
