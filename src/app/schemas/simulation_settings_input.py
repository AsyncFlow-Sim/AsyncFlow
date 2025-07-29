"""define a class with the global settings for the simulation"""

from pydantic import BaseModel, Field

from app.config.constants import (
    EventMetricName,
    SampledMetricName,
    SamplePeriods,
    TimeDefaults,
)


class SimulationSettings(BaseModel):
    """Global parameters that apply to the whole run."""

    total_simulation_time: int = Field(
        default=TimeDefaults.SIMULATION_TIME,
        ge=TimeDefaults.MIN_SIMULATION_TIME,
        description="Simulation horizon in seconds.",
    )

    # These represent the mandatory metrics to collect
    enabled_sample_metrics: set[SampledMetricName] = Field(
        default_factory=lambda: {
            SampledMetricName.READY_QUEUE_LEN,
            SampledMetricName.EVENT_LOOP_IO_SLEEP,
            SampledMetricName.RAM_IN_USE,
            SampledMetricName.EDGE_CONCURRENT_CONNECTION,
        },
        description="Which time-series KPIs to collect by default.",
    )
    enabled_event_metrics: set[EventMetricName] = Field(
        default_factory=lambda: {
            EventMetricName.RQS_LATENCY,
        },
        description="Which per-event KPIs to collect by default.",
    )

    sample_period_s: float = Field(
        default = SamplePeriods.STANDARD_TIME,
        ge = SamplePeriods.MINIMUM_TIME,
        le = SamplePeriods.MAXIMUM_TIME,
        description="constant interval of time to build time series for metrics",
    )

