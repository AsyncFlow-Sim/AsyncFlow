"""
initialization of the structure to gather the sampled metrics
for the client of the system
"""

from collections.abc import Iterable

from app.config.constants import SampledMetricName

# Initialize one time outside the function all possible metrics
# related to the client, the idea of this structure is to
# guarantee scalability in the long term if multiple metrics
# will be considered

CLIENT_METRICS = (
    SampledMetricName.THROUGHPUT_RPS,
)

def build_client_metrics(
    enabled_sample_metrics: Iterable[SampledMetricName],
    ) -> dict[SampledMetricName, list[float | int]]:
    """
    Function to populate a dictionary to collect values for
    time series of sampled metrics related to the client of
    the system.
    """
    # The edge case of the empty dict is avoided since at least
    # one metric is always measured by default.
    return {
        metric: [] for metric in CLIENT_METRICS
        if metric in enabled_sample_metrics
    }
