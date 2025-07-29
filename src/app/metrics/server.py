"""
initialization of the structure to gather the sampled metrics
for the server of the system
"""

from collections.abc import Iterable

from app.config.constants import SampledMetricName

# Initialize one time outside the function all possible metrics
# related to the servers, the idea of this structure is to
# guarantee scalability in the long term if multiple metrics
# will be considered

SERVER_METRICS = (
    SampledMetricName.READY_QUEUE_LEN,
    SampledMetricName.EVENT_LOOP_IO_SLEEP,
    SampledMetricName.RAM_IN_USE,
)

def build_server_metrics(
    enabled_sample_metrics: Iterable[SampledMetricName],
    ) -> dict[SampledMetricName, list[float | int]]:
    """
    Function to populate a dictionary to collect values for
    time series of sampled metrics related to the server of
    the system.
    """
    # The edge case of the empty dict is avoided since at least
    # one metric is always measured by default.
    return {
        metric: [] for metric in SERVER_METRICS
        if metric in enabled_sample_metrics
    }
