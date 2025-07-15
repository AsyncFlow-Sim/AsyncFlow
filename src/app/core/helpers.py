"""helpers for the simulation"""

from collections.abc import Iterable

from app.config.constants import EventMetricName, SampledMetricName


def alloc_sample_metric(
    enabled_sample_metrics: Iterable[SampledMetricName],
    ) -> dict[str, list[float | int]]:
    """
    After the pydantic validation of the whole input we
    instantiate a dictionary to collect the sampled metrics the
    user want to measure
    """
    # t is the alignmente parameter for example assume
    # the snapshot for the sampled metrics are done every 10ms
    # t = [10,20,30,40....] to each t will correspond a measured
    # metric corresponding to that time interval

    dict_sampled_metrics: dict[str, list[float | int]] = {"t": []}
    for key in enabled_sample_metrics:
        dict_sampled_metrics[key] = []
    return dict_sampled_metrics


def alloc_event_metric(
    enabled_event_metrics: Iterable[EventMetricName],
    ) -> dict[str, list[float | int]]:
    """
    After the pydantic validation of the whole input we
    instantiate a dictionary to collect the event metrics the
    user want to measure
    """
    dict_event_metrics: dict[str, list[float | int]]  = {}
    for key in enabled_event_metrics:
        dict_event_metrics[key] = []
    return dict_event_metrics
