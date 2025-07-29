### **FastSim — Simulation Metrics**

Metrics are the lifeblood of any simulation, transforming a series of abstract events into concrete, actionable insights about system performance, resource utilization, and potential bottlenecks. FastSim provides a flexible and robust metrics collection system designed to give you a multi-faceted view of your system's behavior under load.

To achieve this, FastSim categorizes metrics into three distinct types:

1.  **Sampled Metrics (`SampledMetricName`):** These metrics provide a **time-series view** of the system's state. They are captured at fixed, regular intervals (e.g., every 5 milliseconds). This methodology is ideal for understanding trends and measuring the continuous utilization of finite resources. Think of them as periodic snapshots of your system's health.

2.  **Event-based Metrics (`EventMetricName`):** These metrics are raw data points recorded **only when a specific event occurs**, such as the completion of a request. Their collection is asynchronous and irregular. This approach is designed to capture the fundamental data needed for post-simulation analysis with maximum efficiency and flexibility.

3.  **Aggregated Metrics (`AggregatedMetricName`):** These are not collected directly but are **calculated after the simulation ends**. They provide high-level statistical summaries (like mean, median, and percentiles) or rate calculations derived from the raw data collected by event-based metrics. They distill thousands of individual data points into a handful of key performance indicators (KPIs).

The following sections provide a detailed breakdown of each metric within these categories.

-----

### **1. Sampled Metrics: A Time-Series Perspective**

Sampled metrics are configured in the `SimulationSettings` payload. Enabling them allows you to plot the evolution of system resources over time, which is crucial for identifying saturation points and transient performance issues.

| Metric Name (`SampledMetricName`) | Description & Rationale |
| :--- | :--- |
| **`READY_QUEUE_LEN`** | **What it is:** The number of tasks in the event loop's "ready" queue waiting for their turn to run on a CPU core. \<br\>\<br\> **Rationale:** This is arguably the most critical indicator of **CPU saturation**. If this queue length is consistently greater than zero, it means tasks are ready to do work but are forced to wait because the CPU is busy. A long or growing queue is a definitive sign that your application is CPU-bound. |
| **`EVENT_LOOP_IO_SLEEP`** | **What it is:** The number of tasks currently suspended and waiting for an I/O operation to complete (e.g., a database query or a network call). \<br\>\<br\> **Rationale:** This metric helps you determine if your system is **I/O-bound**. If this queue is long, it means the CPU is potentially underutilized because it has no ready tasks to run and is instead waiting for external systems to respond. |
| **`RAM_IN_USE`** | **What it is:** The total amount of memory (in MB) currently allocated by all active requests within a server. \<br\>\<br\> **Rationale:** Essential for **capacity planning and stability analysis**. This metric allows you to visualize your system's memory footprint under load. A steadily increasing `RAM_IN_USE` value that never returns to a baseline is the classic signature of a **memory leak**. |
| **`EDGE_CONCURRENT_CONNECTION`** | **What it is:** The number of requests currently in transit across a network edge. \<br\>\<br\> **Rationale:** This metric helps visualize the load on your network links. A high number of concurrent connections can indicate that downstream services are slow to respond, causing requests to pile up. |

-----

### **2. Event-based Metrics: The Raw Data Foundation**

The goal of event-based metrics is to collect the most fundamental data points with minimal overhead during the simulation. This raw data becomes the single source of truth for all post-simulation transactional analysis.

| Metric Name (`EventMetricName`) | Description & Rationale |
| :--- | :--- |
| **`RQS_CLOCK`** | **What it is:** A collection of `(start_time, finish_time)` tuples, with one tuple recorded for every single request that is fully processed. \<br\>\<br\> **Rationale:** This is the **most efficient and flexible way to capture transactional data**. Instead of storing separate lists for latencies and completion times, we store a single, cohesive data structure. This design choice is deliberate: this raw data is all that is needed to calculate both latency and throughput after the simulation, providing maximum flexibility for analysis. |
| **`LLM_COST`** | **What it is:** A collection of the estimated monetary cost (e.g., in USD) incurred by each individual call to an external Large Language Model (LLM) API. \<br\>\<br\> **Rationale:** In modern AI-powered applications, API calls can be a major operational expense. This metric moves beyond technical performance to measure **financial performance**, allowing for cost optimization. |

-----

### **3. Aggregated Metrics: Post-Simulation Insights**

These metrics are calculated by an analysis module after the simulation finishes, using the raw data from the event-based metrics. This approach provides flexibility and keeps the simulation core lean.

| Metric Name (`AggregatedMetricName`) | Description & Rationale |
| :--- | :--- |
| **`THROUGHPUT_RPS`** | **What it is:** The number of requests successfully completed per second, calculated by aggregating the `finish_time` timestamps from the `RQS_CLOCK` data over a specific time window. \<br\>\<br\> **Rationale:** This is a fundamental measure of **system performance and capacity**. Calculating it post-simulation is superior because the same raw data can be analyzed with different window sizes (e.g., per-second, per-minute) without re-running the simulation. |
| **`LATENCY_STATS`** | **What it is:** Statistical summaries (mean, median, standard deviation, p50, p95, p99) calculated from the `RQS_CLOCK` data by taking `finish_time - start_time` for each tuple. \<br\>\<br\> **Rationale:** These statistics distill thousands of raw data points into key indicators. They tell you about the average user experience (`mean`/`p50`) and, more critically, the worst-case experience (`p95`/`p99`) needed to validate Service Level Objectives (SLOs). |
| **`LLM_STATS`** | **What it is:** Statistical summaries (total cost, average cost per request, etc.) calculated from the raw `LLM_COST` data. \<br\>\<br\> **Rationale:** Provides high-level insights into the financial performance of AI-driven features, enabling strategic decisions on cost optimization. |