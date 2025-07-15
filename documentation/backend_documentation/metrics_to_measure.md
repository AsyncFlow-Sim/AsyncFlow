### **FastSim — simulation's metrics**

Metrics are the lifeblood of any simulation, transforming a series of abstract events into concrete, actionable insights about system performance, resource utilization, and potential bottlenecks. FastSim provides a flexible and robust metrics collection system designed to give you a multi-faceted view of your system's behavior under load.

To achieve this, FastSim categorizes metrics into three distinct types based on their collection methodology:

1.  **Sampled Metrics (`SampledMetricName`):** These metrics provide a **time-series view** of the system's state. They are captured at fixed, regular intervals throughout the simulation's duration (e.g., every second). This methodology is ideal for understanding trends, observing oscillations, and measuring the continuous utilization of finite resources like CPU and RAM. Think of them as periodic snapshots of your system's health.

2.  **Event-based Metrics (`EventMetricName`):** These metrics are recorded **only when a specific event occurs**. Their collection is asynchronous and irregular, triggered by discrete happenings within the simulation, such as the completion of a request. This methodology is perfect for measuring the properties of individual transactions, such as end-to-end latency, where an average value is less important than understanding the full distribution of outcomes.

3.  **Aggregated Metrics (`AggregatedMetricName`):** These are not collected directly during the simulation but are **calculated after the simulation ends**. They provide high-level statistical summaries (like mean, median, and percentiles) derived from the raw data collected by Event-based metrics. They distill thousands of individual data points into a handful of key performance indicators (KPIs) that are easy to interpret.

The following sections provide a detailed breakdown of each metric within these categories, explaining what they measure and the rationale for their importance.

---

### **1. Sampled Metrics: A Time-Series Perspective**

Sampled metrics are configured in the `SimulationSettings` payload. Enabling them allows you to plot the evolution of system resources over time, which is crucial for identifying saturation points and transient performance issues.

| Metric Name (`SampledMetricName`) | Description & Rationale |
| :--- | :--- |
| **`READY_QUEUE_LEN`** | **What it is:** The number of tasks in the `asyncio` event loop's "ready" queue waiting for their turn to run on the CPU. <br><br> **Rationale:** This is arguably the most critical indicator of **CPU saturation**. In a single-threaded Python process, only one coroutine can run at a time (held by the GIL). If this queue length is consistently greater than zero, it means tasks are ready to do work but are forced to wait because the CPU is busy. A long or growing queue is a definitive sign that your application is CPU-bound and that the CPU is a primary bottleneck. |
| **`CORE_BUSY`** | **What it is:** The number of server CPU cores that are currently executing a task. <br><br> **Rationale:** This provides a direct measure of **CPU utilization**. When plotted over time, it shows how effectively you are using your provisioned processing power. If `CORE_BUSY` is consistently at its maximum value (equal to `server_resources.cpu_cores`), the system is CPU-saturated. Conversely, if it's consistently low while latency is high, the bottleneck is likely elsewhere (e.g., I/O). It perfectly complements `READY_QUEUE_LEN` to form a complete picture of CPU health. |
| **`EVENT_LOOP_IO_SLEEP`** | **What it is:** A measure indicating if the event loop is idle, polling for I/O operations to complete. <br><br> **Rationale:** This metric helps you determine if your system is **I/O-bound**. If the event loop spends a significant amount of time in this state, it means the CPU is underutilized because it has no ready tasks to run and is instead waiting for external systems (like databases, caches, or downstream APIs) to respond. High values for this metric coupled with low CPU utilization are a clear signal to investigate and optimize the performance of your I/O operations. |
| **`RAM_IN_USE`** | **What it is:** The total amount of memory (in MB) currently allocated by all active requests within a server. <br><br> **Rationale:** Essential for **capacity planning and stability analysis**. This metric allows you to visualize your system's memory footprint under load. You can identify which endpoints cause memory spikes and ensure your provisioned RAM is sufficient. A steadily increasing `RAM_IN_USE` value that never returns to a baseline is the classic signature of a **memory leak**, a critical bug this metric helps you detect. |
| **`THROUGHPUT_RPS`** | **What it is:** The number of requests successfully completed per second, calculated over the last sampling window. <br><br> **Rationale:** This is a fundamental measure of **system performance and capacity**. It answers the question: "How much work is my system actually doing?" Plotting throughput against user load or other resource metrics is key to understanding your system's scaling characteristics. A drop in throughput often correlates with a spike in latency or resource saturation, helping you pinpoint the exact moment a bottleneck began to affect performance. |

---

### **2. Event-based Metrics: A Per-Transaction Perspective**

Event-based metrics are also enabled in the `SimulationSettings` payload. They generate a collection of raw data points, one for each relevant event, which is ideal for statistical analysis of transactional performance.

| Metric Name (`EventMetricName`) | Description & Rationale |
| :--- | :--- |
| **`RQS_LATENCY`** | **What it is:** The total end-to-end duration, in seconds, for a single request to be fully processed. <br><br> **Rationale:** This is the **primary user-facing performance metric**. Users directly experience latency. While a simple average can be useful, it often hides critical problems. By collecting the latency for *every single request*, FastSim allows for the calculation of statistical distributions and, most importantly, **tail-latency percentiles (p95, p99)**. These percentiles represent the worst-case experience for your users and are crucial for evaluating Service Level Objectives (SLOs) and ensuring a consistent user experience. |
| **`LLM_COST`** | **What it is:** The estimated monetary cost (e.g., in USD) incurred by a single call to an external Large Language Model (LLM) API during a request. <br><br> **Rationale:** In modern AI-powered applications, API calls to third-party services like LLMs can be a major operational expense. This metric moves beyond technical performance to measure **financial performance**. By tracking cost on a per-event basis, you can attribute expenses to specific endpoints or user behaviors, identify unnecessarily costly operations, and make informed decisions to optimize your application's cost-effectiveness. |

---

### **3. Aggregated Metrics: High-Level Summaries**

**Important:** Aggregated metrics are **not configured in the input payload**. They are automatically calculated by the FastSim engine at the end of a simulation run, based on the raw data collected from the enabled Event-based metrics.

| Metric Name (`AggregatedMetricName`) | Description & Rationale |
| :--- | :--- |
| **`LATENCY_STATS`** | **What it is:** A statistical summary of the entire collection of `RQS_LATENCY` data points. This typically includes the mean, median (p50), standard deviation, and high-end percentiles (p95, p99, p99.9). <br><br> **Rationale:** This provides a comprehensive and easily digestible summary of your system's latency profile. While the raw data is essential, these summary statistics answer high-level questions quickly. The mean tells you the average experience, the median protects against outliers, and the p95/p99 values tell you the latency that 95% or 99% of your users will beat—a critical KPI for reliability and user satisfaction. |
| **`LLM_STATS`** | **What it is:** A statistical summary of the `LLM_COST` data points. This can include total cost over the simulation, average cost per request, and cost distribution. <br><br> **Rationale:** This gives you a bird's-eye view of the financial implications of your system's design. Instead of looking at individual transaction costs, `LLM_STATS` provides the bottom line: the total operational cost during the simulation period. This is invaluable for budgeting, forecasting, and validating the financial viability of new features. |