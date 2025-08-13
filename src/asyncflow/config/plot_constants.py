"""Dataclass to define a central structure to plot the metrics"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PlotCfg:
    """Dataclass for the plot of the various metrics"""

    no_data: str
    title:   str
    x_label: str
    y_label: str
    ready_label: str | None = None
    io_label: str | None = None
    legend_label: str | None = None

LATENCY_PLOT = PlotCfg(
    no_data="No latency data",
    title="Request Latency Distribution",
    x_label="Latency (s)",
    y_label="Frequency",
)

THROUGHPUT_PLOT = PlotCfg(
    no_data="No throughput data",
    title="Throughput (RPS)",
    x_label="Time (s)",
    y_label="Requests/s",
)


SERVER_QUEUES_PLOT = PlotCfg(
    no_data="No queue data",
    title="Server Queues",
    x_label="Time (s)",
    y_label="Queue length",
    ready_label="Ready queue",
    io_label="I/O queue",
)

RAM_PLOT = PlotCfg(
    no_data="No RAM data",
    title="RAM Usage",
    x_label="Time (s)",
    y_label="RAM (MB)",
    legend_label="RAM",
)
