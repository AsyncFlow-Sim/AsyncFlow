"""initialization of the structure to gather the metrics for the edges of the system"""

from collections.abc import Iterable

from asyncflow.config.constants import SampledMetricName

# Initialize one time outside the function all possible metrics
# related to the edges, the idea of this structure is to
# guarantee scalability in the long term if multiple metrics
# will be considered

EDGE_METRICS = (
    SampledMetricName.EDGE_CONCURRENT_CONNECTION,
)

def build_edge_metrics(
    enabled_sample_metrics: Iterable[SampledMetricName],
    ) -> dict[SampledMetricName, list[float | int]]:
    """
    Function to populate a dictionary to collect values for
    time series of sampled metrics related to the edges of
    the system.
    """
    # The edge case of the empty dict is avoided since at least
    # one metric is always measured by default.
    return {
        metric: [] for metric in EDGE_METRICS
        if metric in enabled_sample_metrics
    }
